Subject: Blockchain Developer — Joshua Obafemi

Hello,

I am applying for the Blockchain Developer role. I have worked in blockchain
since November 2022, across Celo, Kaia, and most recently Strade Base, where I
shipped the reward layer your brief describes.

**I have already built reward issuance and redemption with real users.** At
Strade Base I designed and shipped a stablecoin on Solana for buying and selling
music rights, along with reward tokens and NFTs carrying on-chain metadata. That
system onboarded 15 artists and serves over 8,000 users. The problems were the
ones you list: who is eligible, what a reward is worth at redemption, how to
settle it, and how to keep the token operations reusable rather than rewritten
per integration. I built those as TypeScript modules for that reason.

**An off-chain event becoming an on-chain entitlement exactly once.** This is
the hard part of your brief and it is what I work on now, building Pesarc, a
cross-border payments system settling on EVM and Solana. I use signed
attestations and idempotency keys rather than trusting the caller: Circle's
Cross-Chain Transfer Protocol for cross-chain value, HMAC-signed webhooks with
replay windows for partner callbacks, and nonce tracking so a retried request
settles once. Your fraud surface differs in kind — a spoofed device is not a
replayed webhook — but the defense has the same shape.

**Blockchain the user does not have to understand.** Pesarc is gasless by
design: ERC-4337 with ERC-7677 paymasters, so a user pays in stablecoin or not
at all. I have worked through sponsored transactions, VerifyingPaymaster, and
the account-recovery problem that follows an embedded wallet. Your brief asks
for blockchain to be "virtually invisible", which I read as a user who does not
learn the word gas and does not lose access by losing a phrase.

**Security as a practice, not a checklist.** I run a daily bug-bounty routine on
Solodit findings. I have also built an invariant-first auditing agent that
automates it: Slither and Aderyn for static analysis, then hypotheses drawn from
per-vertical invariant libraries. A gate refuses to report anything without a
passing Foundry proof-of-concept. Two rules are enforced in code rather than in
prompts — nothing runs against an unauthorized target, and no finding exists
without an executable exploit. The invariant libraries cover the classes you
name: access control, reentrancy including read-only and cross-function, oracle
manipulation, and signature replay.

**Explaining it to people who are not blockchain engineers.** Alongside the
engineering I have spent three years writing developer documentation for Celo,
Kaia, ByBit and Cherry Servers. Celo Academy reached 300,000 views; the Kaia
tutorials onboarded over 5,000 developers. Your brief asks for someone who can
work with product, legal, IoT and AI teams and explain architectural decisions
to them. That is the work I have been doing in parallel the whole time.

On privacy by design, I would want your constraints before proposing a design.
My reading of the brief is that no wellness data belongs on-chain — only a
signed attestation that a rule was met, issued by a service the contract trusts,
with raw events staying in your backend. The chain becomes a settlement record
rather than a health record.

Where I am honest about the gap: I have not worked in health tech, and the
reward system I shipped did not carry emission limits or a long-horizon
redemption budget. I have studied those failure modes — unsustainable issuance,
redemption pressure, reward farming — but studying is not shipping.

Side projects, because they are where I test things before using them at work:

- A multi-agent personal assistant — 18,000 lines of Python, 484 tests,
  deployed on Cloudflare Workers and Containers with Durable Objects, Postgres,
  and Model Context Protocol servers. It verifies Cloudflare Access JWTs at the
  edge before a request reaches the container.
- A football match model that pulls fixtures and results and keeps a public
  record of what it predicted, so the model is scored rather than described.
- The auditing agent above.

github.com/jorshimayor · jorshimayor.is-a.dev · CV attached.

Happy to walk through the attestation design or the proof-of-concept gate.

Best regards,
Joshua Obafemi
