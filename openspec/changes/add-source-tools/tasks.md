## 1. Query

- [ ] 1.1 Add a keyset query on sources: filters, order by id, limit, and a count for the same filter
- [ ] 1.2 Encode and decode the cursor, rejecting anything that isn't one

## 2. Tools

- [ ] 2.1 `list_sources` with the filters, `limit`, `cursor`, `total`, `next_cursor` and the character cap
- [ ] 2.2 `add_source` and `change_source` over the existing store, with the existing validation
- [ ] 2.3 Default both write tools to `ask` in the tool policy

## 3. Tests

- [ ] 3.1 Walk a list of sources across pages with no row missed or repeated, including one added mid-walk
- [ ] 3.2 A bad cursor returns an error, and a page cut by the character cap continues correctly
- [ ] 3.3 Write tools wait for approval and apply the same validation as the HTTP API
