# The writing standard

Distilled from the five editorial documents: the Style Guide, the Structure and
Presentation Guidelines, the User Needs Overview, and the Educate Me / Give Me
Clarity need definitions.

Two things this is not. It is **not a generator** — you research and write, and
this grades what you produced. And it is **not advice**: every rule below traces
to a line in your own guides, and `/api/writing/rules` will tell you which.

Run a draft through `POST /api/writing/check` before it ships. Block-level
findings fail the standard. The judgement calls are returned as questions,
because a linter that pretends to grade structure would produce exactly the
confident, unfalsifiable feedback the style guide warns against.

---

## 1. Pick the user need first

The need determines the structure. Choosing it after writing is how articles end
up as everything the writer knows rather than what the reader came for.

| Category | Need | Answers | Reader leaves able to |
|---|---|---|---|
| Understand | **Educate Me** | What is X? | Hold a conversation on the fundamentals |
| Understand | **Show Me** | What are my options? | See differences at a glance |
| Understand | **Give Me an Overview** | The one-sheeter | Know where to go next |
| Know | **Give Me Clarity** | How does X work? | Explain the mechanism |
| Know | **Give Me Reason** | Why use X? | Decide, with the drawbacks visible |
| Act | **Guide Me** | How do I use X? | Confirm it works |
| Act | **Help Me** | Why isn't this working? | Fix it, or escalate knowingly |

**Understand** assumes no knowledge and explains every term. **Know** respects
existing knowledge, goes deep, and still expands acronyms and reminds the reader
what a term refers to in a subordinate clause. **Act** assumes nothing about the
process and numbers every step.

## 2. Structure

**Inverted pyramid, with the introduction outside it.**

```
Introduction        set up the landscape; give a reason to continue
Lead    (1-2 §)     the primary answer to the title's question
Body    (1-3 §)     supporting information that contextualizes the answer
Tail                additional value; prepares a follow-up article
Next steps          where appropriate — rarely a titled "Conclusion"
```

**The first major section answers the title.** An article called "What Is a
Hypervisor?" opens its first section by saying what a hypervisor is. Burying that
below four sections of context loses the reader before they reach it.

**Do not answer in the introduction either.** State the answer in the opening
paragraph and the reader concludes the remaining 2,000 words are filler and
leaves. The introduction establishes the problem, why it matters, and enough
context to continue — implying the roadmap without announcing it.

> ✗ "In this article, we will discuss what bare metal servers are, how they
>    work, their advantages, and why companies choose them."
>
> ✓ "As businesses scaled workloads on virtual and cloud environments, issues
>    around cost, resource availability, and service stability became prominent
>    concerns…"

**Write for skim readers, not against them.** They scan for the section worth
their time. Once captured they read *more* than someone who started at the top.
Headings are what capture them, which makes structure the most important part of
the piece.

**Each section answers a distinct question.** Test it against the section before
and after: if you cannot say what question this one answers that its neighbours
do not, it should merge or go.

**Order so each section prepares the next.** Context → core concept →
explanation → application → implications, adapted to the need.

**Transitions belong at the end of a section**, implying what comes next without
saying "next we will look at". If transitions are hard to write, the structure is
wrong.

**Progressive disclosure.** Introduce a concept when the reader needs it, after a
clause explaining why it matters. Never introduce several unfamiliar terms in one
paragraph.

> Treat your reader like an escort mission. Go too far too fast and when you turn
> around they are lost several miles back.

## 3. Sentences and paragraphs

- **Headings are the reader's question.** "How Does a Hypervisor Allocate
  Resources?" not "Resource Allocation". Subheadings may be bare nouns, since the
  section has already set the context.
- **Paragraphs: one idea, three or four sentences.** Introduce, develop in the
  context the reader needs, connect back to the section.
- **Vary sentence length.** All-short reads as abrupt, even uncaring. All-long
  forces a re-read, which is the failure to avoid above all others.
- **Active voice**, unless the actor is genuinely unknown or irrelevant.
- **Second person, lightly.** Use "you" for choice and possibility. Avoid it for
  actions and consequences, where it turns into blame.
- **Never first person.** Not "I recommend" but "it is generally recommended to".
- **Expand every acronym on first use**: "virtual dedicated server (VDS)", in
  that order, never reversed.
- **Explain a technical term on first use in a subordinate clause**, so it reads
  as a recap and neither beginner nor expert feels talked down to.
- **American English**, consistently. No mixing within an article.

## 4. Presentation

**Lists** suit requirements, features, examples, advantages, steps, options. They
do not suit continuous explanation. If you are writing your third list, ask
whether it is earning its place or whether it is a habit. Do not turn a
three-item sentence into a list.

**Tables** suit structured comparison. A bare table with no introduction and no
takeaway removes the reader from the article and asks them to re-enter on a
different topic — most will not. Introduce what is being compared, then say what
to conclude from it.

**Density.** For any piece of information ask: does the reader need this? Does it
add value to the purpose? Does it explain what comes before or after? Would
removing it make the article less useful? More than one "no" and it goes.

**Length** follows the reader's purpose. A short article that fully answers the
question beats a long one padded to a target.

## 5. Language never to use

Blocked outright — checked mechanically:

`robust` · `seamless` · `cutting-edge` · `revolutionary` · `game-changing` ·
`world-class` · `next-generation` · `unparalleled` · `best-in-class` ·
`state-of-the-art`

`it is important to note` · `basically` · `essentially` · `in simple terms` ·
`in other words` · `needless to say` · `when it comes to`

Softened, not banned — use a modal (`can` for capability, `may` for possibility,
`should` for recommendation) instead: `always` · `never` · `completely` ·
`guaranteed` · `impossible` · `fastest` · `best` · `cheapest` · `easiest`.

## 6. The final test

> Does this sound like an expert explaining something clearly, in an approachable
> way — or like someone trying to prove they are an expert?

Read it aloud. The article is not a challenge to prove you know the subject; it
is a guide for a reader who has trusted you to get them to the point where they
can hold a conversation about it.

---

## Extending the standard

The five documents cover articles. These extensions apply the same principles to
the other formats — they are derived, not quoted, and are worth arguing with.

### Outline

An outline passes when, reading only the headings, you can tell:

1. Which user need it serves.
2. What question each section answers, and that no two answer the same one.
3. That the first section answers the title.
4. That each section prepares the next.

If the outline reads as a list of topics rather than a sequence of questions, the
article will too.

### Illustration and diagrams

A diagram earns its place by showing a relationship that prose handles badly —
flow, hierarchy, state, or what sits inside what. Rules:

- One idea per diagram. If it needs a key of more than four items, it is two.
- The diagram follows the prose that motivates it and precedes the prose that
  interprets it — the table rule, applied to pictures.
- Label in the article's vocabulary. A diagram introducing new terms creates work
  rather than saving it.
- A screenshot needs the one thing it is showing marked. An unannotated
  screenshot is decoration.

### Video

Video has no skim readers; it has people who leave. The equivalent of a heading
is the first fifteen seconds.

- Open on the problem, not on yourself. No channel throat-clearing.
- Say what the viewer will be able to do by the end, then do not restate it.
- One concept per segment, with the same progressive disclosure as prose.
- Show the thing working before explaining how it works.
- Chapters are headings: name them as the viewer's question.

### Newsletter

- One idea. A newsletter that covers three things is read for none of them.
- The subject line is the heading rule: the reader's question, not a label.
- Open at the specific, not the general. No "in an evolving landscape".
- Earn the link. Say what is on the other side and why it is worth the click.

### Tweets and threads

- The first tweet is the introduction: the problem and a reason to continue,
  never the answer.
- One claim per tweet, each standing alone if quoted.
- Announcing the thread is fine — the exemplar does it. (An earlier
  version of this line said the opposite; it was extrapolation, and wrong.)
- A number, a snippet, or a screenshot beats an adjective. This is where
  `robust` and `game-changing` reappear under pressure — do not let them.
- Close on the concrete next step, not "follow for more".

## The RareSkills method

Derived by reading four of their articles — storage layout, delegatecall, gas
optimization, and the interview question bank — and analysing structure rather
than subject. Select **RARESKILLS** in the profile picker to check against it.

### Where it agrees with the house style

Explanation before code, every time. Progressive complexity: the simple case,
then the real one, then the counterintuitive one. Pitfalls shown happening in an
example rather than warned about in the abstract. Impersonal voice with occasional
second person.

### Where it genuinely disagrees

**RareSkills states the answer in sentence one.** Gas optimization opens: "Gas
optimization in Ethereum is re-writing Solidity code to accomplish the same
business logic while consuming fewer gas units in the EVM." Storage layout opens
by classifying where variables live. Your house style forbids exactly this.

Both are right for their reader. A Cherry Servers reader arrives from search, may
be new, and will leave if they think they have the answer — so the answer *is* the
article, and giving it away ends the visit. A RareSkills reader came deliberately
for a mechanism; the definition is a signpost confirming they are in the right
place, and it costs nothing because the payoff was never the definition. It was
the sixty code blocks below it.

**The rule for choosing:** if a competent reader could act on your one-sentence
answer and close the tab without loss, do not put it in the introduction. If the
value is in the demonstration, state the scope immediately and get to work.

The linter keeps the disagreement rather than resolving it: the roadmap rule is
exempt in the technical profile and enforced in the explanatory one.

### What the technical profile adds

**Every claim is demonstrated.** This is the single most distinctive trait. Gas
optimization quotes "4860 gas vs. 2758 gas" and "saves 2,102 gas". Delegatecall
shows the storage-collision bug happening, with the wrong number on screen.
Storage layout maps bytes to slots in diagrams. A claim about speed, cost or
efficiency with no measurement beside it is **blocked**.

**Prerequisites are declared.** "To fully understand the tricks in this tutorial,
you'll need to understand how the EVM works." "This information is a prerequisite
to understanding how proxies work." Past ~1,200 words, a piece with no statement
of what it assumes is flagged.

**Density of demonstration.** Their articles run 3,500–11,000 words carrying
20–60 runnable blocks. Roughly one per 400 words is the floor. A mechanism
explained only in prose is a summary, and the reader came for the mechanism.

**Hedging is empirical, not verbal.** They do not soften language; they tell you
to measure. "Some gas optimization tricks do not always work." "You should
actually measure the effect." "Test both alternatives." Where a technique is
conditional, say so and hand the reader the benchmark — do not write "may
generally tend to".

**Ends forward, never in summary.** "In Part 2, we will cover…", the next
article, the deeper course. Not a restatement of what was just read.

### Their structural devices, worth stealing

- **Parallel pairs.** Before/after code, Caller/Called contracts. Difference is
  shown side by side rather than described.
- **"Why?" before the counterintuitive result.** A genuine question the reader is
  about to ask, immediately answered — and occasionally left to them: "can you
  figure out why?"
- **Table of contents on anything long.** Their own concession to skim readers.
- **Tiered difficulty.** The interview bank runs Easy → Medium → Hard → Advanced,
  questions only, no answers, each answerable "in three sentences or less". That
  constraint is itself a standard: if your answer needs more than three
  sentences, you have not understood it yet.

## The @Jeyffre standard — and a discovery

**@Jeyffre is Jeffrey Scholz, the founder of RareSkills.** The two standards you
asked for are one person. His bio reads "Building the graduate school of
blockchain engineering @rareskills_io", and the RareSkills method above is his
editorial standard written long. What his account adds is the same epistemics
compressed into posts.

Select **SHORT FORM** to check against it.

### The opener is a claim, not a topic

Every opener is a proposition that could be wrong:

> "Your ability to grind is not what separates you from your peers."
>
> "If you can't explain things well, people are just going to assume you are a
> slop cannon and you don't understand how your own projects work."
>
> "I read Google's paper about their quantum computer so you don't have to."

What fails is an opener with no truth value — "Some thoughts on X", "Let's talk
about X", "A thread about X". There is nothing there to agree or disagree with,
and so no reason to read on.

An earlier version of this rule demanded a **figure** in the first line. It was
derived from one thread and a wider sample refuted it: four of his six openers
carry no number at all. The rule is now about propositions, and his own openers
are in the test suite precisely so an overfitted rule fails loudly next time.

### Wrong answer first, then refine

His most distinctive device:

> "Your ability to grind is **not** what separates you from your peers. In India,
> Singapore, and China, grinding is part of the culture. Grinding is **necessary
> but not sufficient**. Your ability to grind *with uncertain and delayed
> payoffs* is what separates you."

State the belief the reader probably holds, name the specific counter-evidence
(three countries, not "many places"), then give the refinement. The reader arrives
at the answer having watched the wrong one fail.

Note the vocabulary: **necessary but not sufficient**, **prerequisites**, **phase
transition**. Exact logical terms used exactly.

### Exhaustive enumeration

> "If you are not learning as fast as you want to, there are **only three
> possible reasons**: 1) You lack the prerequisites… 2) You lack good…"

A stated count is a promise. The linter flags a count the post does not deliver,
because "only three reasons" followed by two reads as an unfinished draft.

### Superlatives are allowed — backed

He writes "RareSkills has the **best** writers and the industry's **best** writing
process", which your house style bans outright. The next line is why it survives:

> "People understand our articles exactly the way we intend them to."

The claim is not the problem; the bare claim is. In this profile the blanket
superlative ban is replaced by `unbacked_superlative`: a superlative with no
reason beside it.

### Vague words are the enemy, explicitly

His objection to another post was that the word "just" "glosses over a lot of
physical constraints", answered with three concrete parallels: "You can't 'just'
build an app or 'just' start a company or 'just' invade another country."

So size and intensity words standing in for a measurement are **blocked** in this
profile: `huge` · `massive` · `insane` · `a lot of` · `incredibly` · `extremely`.
Where he makes a claim, the number is in the sentence — "$3,000", "$200 plan",
"5 minutes".

### The stake is stated

"I'm the founder of @RareSkills_io." Said outright, which is what makes a
recommendation usable. Promoting something you profit from without saying so is
flagged.

### Where this profile disagrees with the article rules

**First person is the form, not a failure.** "I read Google's paper", "I propose",
"I don't get". The article ban on first person exists to stop opinion being
dressed as authoritative recommendation — a problem that does not arise when the
whole post is visibly one person's view.

**Announcing the thread is fine.** My earlier extrapolation in this document said
never announce a thread as a thread. He ends with "I will break it down.🧵". The
exemplar beats my extrapolation, and that earlier guidance was wrong — it is now
corrected here and exempted in the linter.

**Article structure rules do not apply.** No sections, no heading style, no table
framing. Demanding them would fail every post ever written.

What does survive is the marketing ban. He does not write `robust`,
`game-changing` or `revolutionary` in any register.

### The test

His own opener, run through this profile, passes with zero findings. A standard
that fails the writing it was derived from is wrong, and there is a test pinning
exactly that.

## What is still missing

The sample is now thirteen posts, which is enough for the rules above — every one
of them recurs across several. Two gaps remain.

**The close.** Most posts in the sample are truncated by "Show more", so how he
lands a long thread is still unknown. The rules say nothing about it.

**Register range.** The sample is opinion and argument. His technical threads
almost certainly behave differently, closer to the RareSkills article method, and
nothing here distinguishes the two.

If either matters, paste the full text of three or four threads you rate and the
same extraction can run over them. The method is the one used here: read
structure, never style; check every derived rule against the source writing; and
throw the rule away when the writing contradicts it.
