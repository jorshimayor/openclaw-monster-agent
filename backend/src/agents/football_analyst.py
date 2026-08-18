from __future__ import annotations

from typing import Any, Dict, List

from ..core.types import AgentRole, AgentResult
from ..core.logging import get_logger
from .base import Agent, Tool
from ._utils import _call_tool, tool_matches

logger = get_logger(__name__)


class FootballAnalystAgent(Agent):
    role: AgentRole = AgentRole.FOOTBALL
    model_profile: str = "groq/llama-3.1-8b-instant"
    tool_allowlist: List[str] = [
        "google_workspace.sheets_write",
        "google_workspace.sheets_read",
        "google_workspace.write_sheet",
        "slack.send_message",
        "notion.*",
    ]
    soul_path: str = "src/souls/football_analyst.md"

    async def invoke(
        self, context: Dict[str, Any], tools: List[Tool], llm,
        extra_llm_kwargs: Optional[Dict[str, Any]] = None,
    ) -> AgentResult:
        fixture = context.get("fixture") or context.get(
            "match", context.get("description", "No fixture provided.")
        )
        home = context.get("home_team", "Home Team")
        away = context.get("away_team", "Away Team")
        league = context.get("league", "Competition")
        date = context.get("match_date", "TBD")
        data_points = context.get(
            "data",
            {
                "xg_home": 0.0,
                "xg_away": 0.0,
                "possession_home": 50,
                "shots_on_target_home": 0,
                "shots_on_target_away": 0,
            },
        )
        extra = context.get("extra_instructions", "")
        mcp_transport = context.get("mcp_transport")
        tool_names = [t.name for t in tools] if tools else []

        prompt = self._build_prompt(
            {
                "fixture": fixture,
                "home": home,
                "away": away,
                "league": league,
                "date": date,
                "data_points": data_points,
            },
            extra_instructions=(
                f"{extra}\nProduce a DATA-DRIVEN structured football match report in markdown. "
                f"Use EXACTLY these sections:\n"
                f"# Match Report: {home} vs {away}\n"
                f"## Match Metadata (league, date, venue-hint)\n"
                f"## Expected Goals & Key Stats TABLE (rows: xG, xGA, possession, SoT, corners, fouls, cards)\n"
                f"## Tactical Breakdown (home approach, away approach, key duels)\n"
                f"## Player Spotlight (1 per team, with data backing)\n"
                f"## Verdict & xG-based Score Projection\n"
                f"## Post-Match Action Items (for coaches / analysts)\n"
                f"Rank confidence in each projection as 0.00-1.00 inline. Anchor all claims to the data_points provided."
            ),
        )

        try:
            result = await llm.generate(prompt, self.role, **(extra_llm_kwargs or {}))
            output = result["response"]
            confidence = 0.82
            errors = None
        except Exception as e:
            logger.error("football_analyst_invoke_error", error=str(e))
            xg_h = data_points.get("xg_home", 0)
            xg_a = data_points.get("xg_away", 0)
            fallback = (
                f"# Match Report: {home} vs {away}\n\n"
                f"## Match Metadata\n"
                f"- League: {league}\n- Date: {date}\n\n"
                f"## Expected Goals & Key Stats\n"
                f"| Stat | {home} | {away} |\n"
                f"|------|--------|--------|\n"
                f"| xG | {xg_h} | {xg_a} |\n"
                f"| Possession % | {data_points.get('possession_home', 50)} | {100 - int(data_points.get('possession_home', 50))} |\n\n"
                f"## Tactical Breakdown\n"
                f"Initial draft: Provisionally assess styles based on xG delta of {abs(float(xg_h) - float(xg_a)):.2f}\n\n"
                f"## Verdict\n"
                f"xG-projected result leaning toward {'home' if float(xg_h) > float(xg_a) else 'away' if float(xg_a) > float(xg_h) else 'draw'} (confidence 0.60).\n\n"
                f"_Fallback report; LLM error: {e}"
            )
            output = fallback
            confidence = 0.48
            errors = [str(e)]

        try:
            has_sheet_write = (
                "google_workspace.write_sheet" in tool_names
                or "google_workspace.sheets_write" in tool_names
                or any(
                    tool_matches(self.tool_allowlist, n)
                    and ("write_sheet" in n or "sheets_write" in n)
                    for n in tool_names
                )
            )
            if has_sheet_write:
                sheet_result = await _call_tool(
                    "google_workspace.write_sheet",
                    {
                        "spreadsheet_id": context.get("sheet_id", "default-stats-sheet"),
                        "sheet_name": f"{home}-vs-{away}-{date}",
                        "rows": [
                            ["Stat", home, away],
                            ["xG", data_points.get("xg_home", 0), data_points.get("xg_away", 0)],
                            ["Possession %", data_points.get("possession_home", 50), 100 - int(data_points.get("possession_home", 50))],
                            ["SoT", data_points.get("shots_on_target_home", 0), data_points.get("shots_on_target_away", 0)],
                        ],
                    },
                    transport=mcp_transport,
                )
                if sheet_result.get("skipped"):
                    logger.info(
                        "football_analyst_sheet_write_skipped",
                        reason=sheet_result.get("reason"),
                    )
                else:
                    logger.info(
                        "football_analyst_would_write_stats_to_sheet",
                        home=home,
                        away=away,
                    )
                    output = output + "\n\n---\n[FootballAnalystAgent] would write stats to Google Sheet (tool available)."
        except Exception as sheet_err:
            logger.warning("football_analyst_sheet_write_failed", error=str(sheet_err))

        return AgentResult(
            agent_role=self.role,
            output=output,
            confidence=confidence,
            errors=errors,
        )
