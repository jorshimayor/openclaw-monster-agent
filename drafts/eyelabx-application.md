Subject: Blockchain Developer — Joshua Obafemi

Hello,

I have been building on blockchains since November 2022. I am currently
cofounder and CTO of OnchainSuite, and before that I shipped a reward and
redemption system close to the one your brief describes.

OnchainSuite is a lifecycle engine for blockchain companies: it watches wallet
activity across Ethereum, Base, Arbitrum, Optimism and Polygon, and turns it
into something a growth team can act on. I own the architecture, the
infrastructure, the engineering standards, deployment and security. Three parts
of that are the same problems your brief lists. We resolve identity, merging
wallets, emails and app accounts into one customer record — which is the same
machinery you need to stop one person farming rewards from six accounts. We
ingest verified events from contracts and from customers' own backends through a
server-to-server API and an automation trigger endpoint, which is the shape of
taking wellness events from a desktop app and later a wearable. And because
partners push data to us, I built the key management around it: publishable and
secret keys, scoped, rotatable, with the delivery of every message auditable
afterwards.

Before that, at Strade Base, I designed a stablecoin on Solana for buying and
selling music rights and built the reward tokens and NFTs around it, with their
metadata held on-chain. It serves over 8,000 users and onboarded 15 artists. The
questions that took the time are yours: who is eligible, what a reward is worth
when someone redeems it, how it settles, and how to write token operations once
rather than again for every integration.

Neither of those pushed hard on the part your brief turns on: an off-chain
event becoming an on-chain entitlement exactly once. That is
what I work on now, building Pesarc, a cross-border payments system settling on
EVM and Solana, where every payout traces to something that happened elsewhere
and must not be claimed twice. The approach is to trust a signature rather than
a caller: Circle's Cross-Chain Transfer Protocol for cross-chain value,
HMAC-signed webhooks with replay windows for partner callbacks, and nonce
tracking so a retried request settles once. Your fraud surface differs in kind,
since a spoofed wearable is not a replayed webhook, but the defense has the same
shape.

Pesarc also has to disappear, which is your other requirement. It is gasless by
design, ERC-4337 with ERC-7677 paymasters, so a user pays in stablecoin or not
at all. I have worked through sponsored transactions, VerifyingPaymaster, and
the account-recovery problem that arrives the moment a wallet is embedded rather
than installed. When your brief says blockchain should be "virtually invisible",
I read that as a user who does not have to learn the word gas, and does not lose
their rewards by losing a phrase.

Underneath all of it is the security practice, because a reward system is a
system that pays out, and anything that pays out gets attacked. I work through
Solodit findings daily. To make that systematic I built an invariant-first
auditing agent: Slither and Aderyn for the cheap static pass, then hypotheses
drawn from per-vertical invariant libraries. A gate refuses to report anything
without a passing Foundry proof-of-concept. Two rules live in code rather than
in a prompt — nothing runs against an unauthorized target, and no finding exists
without an executable exploit. The libraries cover the classes you name: access
control, reentrancy including read-only and cross-function, oracle manipulation,
and signature replay.

The last part is harder to show in a repository. For three years I wrote
developer documentation alongside the engineering, for Celo, Kaia, ByBit and
Cherry Servers. Celo Academy passed 300,000 views and the Kaia tutorials
onboarded more than 5,000 developers. Your brief asks for someone who can sit
with product, legal, IoT and AI teams and explain why an architecture is shaped
the way it is. That is what I have been doing in parallel the whole time, and it
is why I would push back on anything putting wellness data on-chain. My reading
is that none of it belongs there — only a signed attestation that a rule was
met, issued by a service the contract trusts, with raw events staying in your
backend. The chain becomes a settlement record instead of a health record. I
would want your constraints before committing to that.

Two things I cannot claim. I have not worked in health tech. And the reward
system I shipped carried no emission limits or long-horizon redemption budget,
which your brief asks for by name. I have read enough about unsustainable
issuance, redemption pressure and reward farming to know what I would be walking
into, but reading is not shipping and you should weigh it that way.

onchainsuite.com · github.com/jorshimayor · jorshimayor.is-a.dev · CV attached.

I would be glad to walk through the attestation design, or the proof-of-concept
gate, in more detail.

Best regards,
Joshua Obafemi
