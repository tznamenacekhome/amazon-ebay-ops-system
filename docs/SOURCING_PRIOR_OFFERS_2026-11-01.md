# Repeat opportunities and buyer offer history

The two repeats placed on Watch on November 1 were Sonic and the Secret Rings
(`137887648197`, prior offer $17) and Marvel's Avengers (`403002608732`, $19).
The operator confirms both offers were declined. Their current profitable offer
limits were $15.96 and $15.94. Existing hourly imports succeeded, but eBay's
live BestOfferList returned the amounts with **no BestOfferStatus element**.
The old importer correctly refused to invent a decline, but discarded the
unknown-status offer entirely, allowing the listings to qualify again.

The additive migration `20261102011542_mbop_sourcing_unresolved_buyer_offers.sql`
retains missing-status offers separately from confirmed declines. Both server
scoring and web presentation read the maximum amount from
`vw_sourcing_offer_limits`. USD and variation safeguards remain. A best-offer
listing is suppressed when its current maximum offer is no higher than that
amount; a genuinely higher profitable offer or qualifying buy-now price can
still qualify. Unknown statuses are never represented as confirmed declines.
History is keyed by exact eBay listing, across runs and ASINs, without expiry.
Watch actions and operator matching feedback remain intact.

On-demand sourcing checks/imports buyer history before scoring in both single
and progressive modes, including Continue. A failed history check fails the
run. Existing hourly scheduled imports also write the separate evidence.
The web reads retained evidence rather than making hundreds of live eBay
requests on each page load. Previously cached pages require Refresh.

No eBay offers are submitted or modified. The new table has RLS and server-only
grants; the aggregate view uses security_invoker. The existing explicit-decline
table and guarded decision RPCs retain their confirmed-decline semantics.
