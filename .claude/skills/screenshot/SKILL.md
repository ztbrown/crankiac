---
name: screenshot
description: Take a screenshot of a web page and analyze it for UI issues. Use when testing UI changes, verifying visual appearance, or debugging frontend problems.
disable-model-invocation: false
allowed-tools: mcp__puppeteer-mcp-claude__puppeteer_launch, mcp__puppeteer-mcp-claude__puppeteer_new_page, mcp__puppeteer-mcp-claude__puppeteer_navigate, mcp__puppeteer-mcp-claude__puppeteer_screenshot, mcp__puppeteer-mcp-claude__puppeteer_close_page, mcp__puppeteer-mcp-claude__puppeteer_close_browser, mcp__puppeteer-mcp-claude__puppeteer_wait_for_selector, mcp__puppeteer-mcp-claude__puppeteer_evaluate, Read
---

# UI Screenshot Skill

Take a screenshot of a web page and analyze it for common UI issues.

## Arguments

`$ARGUMENTS` is the URL to screenshot. Defaults to `http://localhost:5000` if not provided.

## Workflow

### Step 1: Launch Browser

Launch a headless Chrome browser:

```
puppeteer_launch with headless: true
```

### Step 2: Create Page and Navigate

Create a new page and navigate to the target URL:

```
puppeteer_new_page with pageId: "screenshot-page"
puppeteer_navigate with pageId: "screenshot-page", url: <target-url>
```

Use the URL from `$ARGUMENTS` if provided, otherwise default to `http://localhost:5000`.

### Step 3: Wait for Page Load

Wait for the page to stabilize. Use `puppeteer_wait_for_selector` for key elements, or use `puppeteer_evaluate` to check document ready state:

```javascript
document.readyState === 'complete'
```

### Step 4: Take Screenshot

Capture the page:

```
puppeteer_screenshot with pageId: "screenshot-page", fullPage: true
```

### Step 5: Analyze Screenshot

After viewing the screenshot, analyze it for these common issues:

**Layout Issues:**
- Elements overlapping or misaligned
- Content cut off or overflowing containers
- Broken responsive layouts
- Missing spacing/padding

**Visual Issues:**
- Missing or broken images
- Incorrect colors or styling
- Font rendering problems
- Empty sections that should have content

**Functional Indicators:**
- Error messages displayed
- Loading spinners stuck
- Empty states that seem incorrect
- Forms with validation errors

**Accessibility Concerns:**
- Text too small or low contrast
- Missing focus indicators
- Buttons too small for touch

### Step 6: Report Findings

Provide a structured report:

```
## Screenshot Analysis: <url>

### Status: [OK | WARNING | ERROR]

### Screenshot
[The captured image]

### Observations
- [List what you observed]

### Issues Found
- [List any problems detected, or "None detected"]

### Recommendations
- [Any suggested fixes, or "No action needed"]
```

### Step 7: Clean Up

Always close the browser when done:

```
puppeteer_close_browser
```

## Example Usage

```
/screenshot
/screenshot http://localhost:5000/search
/screenshot http://localhost:3000/episodes/123
```

## Error Handling

If the page fails to load:
1. Check if the server is running
2. Verify the URL is correct
3. Report the error with any console messages

If screenshot fails:
1. Try reducing viewport size
2. Wait longer for page load
3. Report the specific error
