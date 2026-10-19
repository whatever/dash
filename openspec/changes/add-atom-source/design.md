## Context

`Web` fetches a URL and hands the body to `parse`, which subclasses override. Hacker News and Bushwick Daily are `Web` subclasses that return one item per story or article. An Atom feed fits the same shape.

## Goals / Non-Goals

**Goals**
- One item per feed entry, with a key that stays the same while the entry exists.

**Non-Goals**
- RSS or JSON Feed. They can follow as their own kinds if wanted.
- Changing what happens to an item after it is queued.

## Decisions

**A `Web` subclass.** Fetching, the HTTP client and error handling are already in `Web`; only `parse` differs, as it does for the site-specific kinds.

**Key by `id`, then link.** Atom requires an `id` on every entry, but real feeds sometimes omit it. The link is the next most stable value.

**Detect feeds by the `.atom` suffix in the UI.** Hosts identify Hacker News and Bushwick Daily, but a feed can live on any host. A suffix is a cheap hint that covers GitHub's feeds. Other feeds can be added with the API directly.

**Stdlib XML parser.** Expat 2.4.1 and later guard against entity-expansion attacks, so no extra dependency is needed.

## Risks / Trade-offs

- A feed whose URL does not end in `.atom` has to be added as kind `atom` through the API; the panel will add it as a page.
- Summaries are cut at the same 1,000 characters as pages.
