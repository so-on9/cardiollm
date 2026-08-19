const { chromium } = require("playwright");

const baseUrl = process.env.CARDIOLLM_CHECK_URL || "https://echollm.thu.edu.tw";
const password = process.env.UI_PASSWORD;
const outputDir = process.env.CARDIOLLM_CHECK_OUTPUT || "/artifacts";

if (!password) {
  throw new Error("UI_PASSWORD is required for the visual check");
}

async function login(page) {
  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  if (await page.locator("#pw").isVisible().catch(() => false)) {
    await page.locator("#pw").fill(password);
    await page.locator("#btn").click();
  }
  await page.locator(".app-shell").waitFor({ state: "visible", timeout: 30000 });
}

async function inspect(page, label) {
  const metrics = await page.evaluate(() => {
    const viewportWidth = window.innerWidth;
    const overflow = [...document.querySelectorAll("body *")]
      .filter((element) => {
        const style = getComputedStyle(element);
        if (
          style.display === "none" ||
          style.visibility === "hidden" ||
          Number(style.opacity) === 0
        ) {
          return false;
        }
        const rect = element.getBoundingClientRect();
        return rect.width > 0 && (rect.right > viewportWidth + 2 || rect.left < -2);
      })
      .slice(0, 12)
      .map((element) => ({
        tag: element.tagName,
        className: element.className,
        rect: element.getBoundingClientRect().toJSON(),
      }));

    return {
      viewport: [window.innerWidth, window.innerHeight],
      documentWidth: document.documentElement.scrollWidth,
      horizontalOverflow: document.documentElement.scrollWidth > viewportWidth + 1,
      visibleOverflowElements: overflow,
      rootMounted: Boolean(document.querySelector(".app-shell")),
      reportHeight: document.querySelector(".report-panel")?.getBoundingClientRect().height,
      visualizerHeight: document
        .querySelector(".visualizer-panel")
        ?.getBoundingClientRect().height,
    };
  });
  console.log(JSON.stringify({ label, ...metrics }));
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    ignoreHTTPSErrors: true,
    viewport: { width: 1440, height: 1000 },
  });
  const page = await context.newPage();
  const consoleErrors = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => consoleErrors.push(error.message));

  await login(page);
  await page.waitForTimeout(800);
  await inspect(page, "desktop");
  await page.screenshot({
    path: `${outputDir}/cardiollm-desktop.png`,
    fullPage: true,
  });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(500);
  await inspect(page, "mobile");
  await page.screenshot({
    path: `${outputDir}/cardiollm-mobile.png`,
    fullPage: true,
  });

  await page.locator(".workspace-topbar .mobile-only").first().click();
  await page.waitForTimeout(400);
  const drawerOpen = await page.locator(".control-rail.is-open").isVisible();
  console.log(JSON.stringify({ label: "mobile-drawer", drawerOpen }));
  await page.screenshot({
    path: `${outputDir}/cardiollm-mobile-drawer.png`,
    fullPage: false,
  });

  await page.locator(".rail-heading .mobile-only").click();

  const structured = {
    version: "1.0",
    findings: [
      {
        part: "LV",
        condition: "dilatation",
        severity: "moderate",
        status: "present",
      },
    ],
    measurements: [],
    overall: { summary: "左心室中度擴大", has_abnormality: true },
  };
  const streamEvents = [
    {
      event: "phase_start",
      phase: "translate",
      label: "翻譯模型推論中",
      progress: 8,
    },
    { event: "token", phase: "translate", delta: "左心室擴大" },
    {
      event: "phase_done",
      phase: "translate",
      text: "左心室擴大",
      progress: 48,
    },
    {
      event: "phase_start",
      phase: "summary",
      label: "摘要模型推論中",
      progress: 54,
    },
    { event: "token", phase: "summary", delta: "左心室中度擴大" },
    {
      event: "phase_done",
      phase: "summary",
      text: "左心室中度擴大",
      progress: 88,
    },
    {
      event: "phase_start",
      phase: "extract_json",
      label: "結構化 JSON 解析中",
      progress: 92,
    },
    {
      event: "phase_done",
      phase: "extract_json",
      structured,
      progress: 97,
    },
    { event: "done", progress: 100, structured },
  ];
  await page.route("**/pipeline_stream", (route) =>
    route.fulfill({
      status: 200,
      contentType: "text/plain; charset=utf-8",
      body: `${streamEvents.map((event) => JSON.stringify(event)).join("\n")}\n`,
    }),
  );
  await page.locator(".report-panel textarea").fill("LV CHAMBER DILATATION");
  await page.locator(".mobile-action-bar .button.primary").click();
  await page.waitForFunction(
    () =>
      document
        .querySelector(".result-panel:nth-of-type(2) .result-content")
        ?.textContent.includes("左心室中度擴大"),
  );
  await page.waitForTimeout(1100);
  const streamSmoke = await page.evaluate(() => ({
    translation: document
      .querySelector(".result-panel:nth-of-type(1) .result-content")
      ?.textContent.trim(),
    summary: document
      .querySelector(".result-panel:nth-of-type(2) .result-content")
      ?.textContent.trim(),
    structuredReady: document.querySelector(".json-status")?.textContent === "解析完成",
  }));
  console.log(JSON.stringify({ label: "pipeline-stream", ...streamSmoke }));

  await page.getByRole("tab", { name: "AI 繪圖" }).click();
  const aiWorkspaceVisible = await page.locator(".ai-workspace").isVisible();
  await page.getByRole("tab", { name: "JSON" }).click();
  const jsonVisible = await page.locator(".structured-panel.mobile-active").isVisible();
  console.log(
    JSON.stringify({
      label: "mobile-interactions",
      aiWorkspaceVisible,
      jsonVisible,
    }),
  );

  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  await page.locator(".workspace-topbar .mobile-only").first().click();
  await page.getByRole("button", { name: "登出" }).click();
  await page.locator("#pw").waitFor({ state: "visible", timeout: 15000 });
  const logoutScrollY = await page.evaluate(() => window.scrollY);
  console.log(JSON.stringify({ label: "logout", scrollY: logoutScrollY }));

  console.log(JSON.stringify({ label: "console-errors", errors: consoleErrors }));
  await browser.close();
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
