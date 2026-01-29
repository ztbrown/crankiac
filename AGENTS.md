# Agent Instructions

This project uses **bd** (beads) for issue tracking. Run `bd onboard` to get started.

## Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --status in_progress  # Claim work
bd close <id>         # Complete work
bd sync               # Sync with git
```

## Puppeteer Browser Automation

Puppeteer MCP tools are available for browser automation tasks. Use these for web scraping, testing, and interacting with web pages.

### Available Tools

| Tool | Purpose |
|------|---------|
| `puppeteer_launch` | Launch a new browser instance |
| `puppeteer_new_page` | Create a new page/tab |
| `puppeteer_navigate` | Navigate to a URL |
| `puppeteer_click` | Click on an element by selector |
| `puppeteer_type` | Type text into an input field |
| `puppeteer_get_text` | Extract text content from an element |
| `puppeteer_screenshot` | Capture a screenshot |
| `puppeteer_evaluate` | Execute JavaScript in page context |
| `puppeteer_wait_for_selector` | Wait for an element to appear |
| `puppeteer_close_page` | Close a specific page |
| `puppeteer_close_browser` | Close the browser and all pages |
| `puppeteer_set_cookies` | Set cookies for a page |
| `puppeteer_get_cookies` | Get cookies from a page |
| `puppeteer_delete_cookies` | Delete cookies |
| `puppeteer_set_request_interception` | Enable request/response interception |

### Basic Workflow

```
1. Launch browser:     puppeteer_launch (headless: true)
2. Create page:        puppeteer_new_page (pageId: "main")
3. Navigate:           puppeteer_navigate (pageId: "main", url: "https://...")
4. Interact:           puppeteer_click, puppeteer_type, etc.
5. Extract data:       puppeteer_get_text, puppeteer_evaluate
6. Clean up:           puppeteer_close_browser
```

### Best Practices

- **Always use headless mode** (`headless: true`) unless debugging requires visual inspection
- **Always close the browser** when done - use `puppeteer_close_browser` to clean up
- **Use unique pageIds** when working with multiple pages
- **Wait for elements** before interacting - use `puppeteer_wait_for_selector` before click/type
- **Handle navigation events** - use `waitUntil: "networkidle0"` for pages with async loading

### Common Patterns

**Scraping text from a page:**
```
1. puppeteer_launch()
2. puppeteer_new_page(pageId: "scrape")
3. puppeteer_navigate(pageId: "scrape", url: "...")
4. puppeteer_wait_for_selector(pageId: "scrape", selector: ".content")
5. puppeteer_get_text(pageId: "scrape", selector: ".content")
6. puppeteer_close_browser()
```

**Filling a form:**
```
1. puppeteer_launch()
2. puppeteer_new_page(pageId: "form")
3. puppeteer_navigate(pageId: "form", url: "...")
4. puppeteer_type(pageId: "form", selector: "#email", text: "...")
5. puppeteer_type(pageId: "form", selector: "#password", text: "...")
6. puppeteer_click(pageId: "form", selector: "button[type=submit]")
7. puppeteer_close_browser()
```

**Taking a screenshot:**
```
1. puppeteer_launch()
2. puppeteer_new_page(pageId: "shot")
3. puppeteer_navigate(pageId: "shot", url: "...")
4. puppeteer_screenshot(pageId: "shot", path: "/tmp/screenshot.png", fullPage: true)
5. puppeteer_close_browser()
```

### Troubleshooting

| Issue | Solution |
|-------|----------|
| Element not found | Use `puppeteer_wait_for_selector` before interacting |
| Page not loading | Try `waitUntil: "networkidle0"` or increase timeout |
| Browser already running | Call `puppeteer_close_browser` first |
| Stale page reference | Verify pageId matches an open page |
| Blocked by site | Try `stealth: true` in launch options |
| Slow performance | Block unnecessary resources with `puppeteer_set_request_interception` |

### Request Interception

Block unnecessary resources to speed up scraping:

```
puppeteer_set_request_interception(
  pageId: "main",
  enable: true,
  blockResources: ["image", "stylesheet", "font", "media"]
)
```

## Landing the Plane (Session Completion)

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   bd sync
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds

