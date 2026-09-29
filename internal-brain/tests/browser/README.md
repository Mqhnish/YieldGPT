# Employee interface browser checks

These checks use the actual employee interface and a running application. They sign in as demo personas, ask ordinary questions, and then intercept selected browser responses to exercise unsafe source text and delayed responses. They do not modify source content or permissions. Ordinary requests will appear in the audit log.

## Prerequisites

- Start the application with `IB_DEMO_MODE=1` and its seeded Company A data.
- Use a local development instance, not a production service.
- Install Node.js 20+ and Playwright in this folder:

```sh
npm install --prefix tests/browser --no-save playwright
npx --prefix tests/browser playwright install chromium
```

## Run

From the project root:

```sh
node tests/browser/employee-ui.mjs
```

The default address is `http://127.0.0.1:8765`. To use a different address:

```sh
APP_URL=http://127.0.0.1:8000 node tests/browser/employee-ui.mjs
```

If using an already installed Chrome executable, set `CHROME_PATH` to its full path. Otherwise Playwright uses its installed Chromium browser.

```sh
APP_URL=http://127.0.0.1:8000 CHROME_PATH=/path/to/chrome node tests/browser/employee-ui.mjs
```

## Coverage

- Real login and current user identity; visible source/generation modes.
- Ordinary employees cannot see an administration navigation link.
- A real migration answer includes clickable citations and current evidence.
- Source drawer closes with Escape and permits only HTTPS source links.
- Switching accounts clears the prior question, answer, and source content.
- The contractor’s restricted query returns no source metadata.
- HTML supplied in answers, source titles, and passages is displayed as inert text.
- `javascript:` source URLs never become links.
- A delayed answer from the previous user cannot render after switching accounts.
- The mobile layout has no horizontal overflow and supports sign-out.
- Tokens and answers are not written to local or session storage.
- The full flow produces no unhandled browser JavaScript errors.

These are interface tests. The Python suite remains responsible for server-side authorization, retrieval, grounding, freshness, and audit behavior. The tests require the demo personas and a migration query that returns at least one source.
