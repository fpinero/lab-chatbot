import { expect, test, type Page } from "@playwright/test";

async function signIn(page: Page) {
  await page.goto("/");
  await page
    .getByLabel("Owner passphrase")
    .fill("synthetic-browser-passphrase");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByLabel("Message", { exact: true })).toBeVisible();
}

async function navigation(page: Page) {
  const opener = page.getByRole("button", {
    name: "Open navigation",
    exact: true,
  });
  if (await opener.isVisible()) await opener.click();
}

async function begin(page: Page) {
  await navigation(page);
  const [response] = await Promise.all([
    page.waitForResponse(
      (r) =>
        r.url().endsWith("/api/temporary-chats") &&
        r.request().method() === "POST",
    ),
    page.getByRole("button", { name: "Temporary chat", exact: true }).click(),
  ]);
  expect(response.status()).toBe(201);
  await expect(
    page.getByText("Temporary · Not saved", { exact: true }),
  ).toBeVisible();
  return (await response.json()).id as string;
}

test("temporary image chats preserve useful controls without creating history and discard on exit", async ({
  page,
}, info) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await signIn(page);
  const before = await (await page.request.get("/api/conversations")).json();
  const id = await begin(page);
  const requests: string[] = [];
  page.on("request", (r) => {
    if (r.method() === "POST") requests.push(new URL(r.url()).pathname);
  });
  const buffer = Buffer.from(
    await page.evaluate(() => {
      const canvas = document.createElement("canvas");
      canvas.width = 800;
      canvas.height = 500;
      const ctx = canvas.getContext("2d")!;
      ctx.fillStyle = "#eeeecc";
      ctx.fillRect(0, 0, 800, 500);
      ctx.fillStyle = "#254535";
      ctx.font = "32px sans-serif";
      ctx.fillText("Synthetic temporary screenshot", 30, 80);
      return canvas.toDataURL("image/png").split(",")[1];
    }),
    "base64",
  );
  await page.getByLabel("Attach files to chat", { exact: true }).setInputFiles({
    name: "private-fixture.png",
    mimeType: "image/png",
    buffer,
  });
  const picker = page.locator(".compact-picker");
  await expect(
    picker.getByText("private-fixture.png", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Send message", exact: true }),
  ).toBeDisabled();
  await picker
    .getByRole("button", {
      name: "Preview image: private-fixture.png",
      exact: true,
    })
    .click();
  await expect(
    page.getByRole("dialog", { name: "private-fixture.png", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Close image preview", exact: true })
    .click();
  await page.getByText("Options", { exact: true }).click();
  await picker
    .getByLabel("System prompt", { exact: true })
    .fill("Analyze this synthetic private screenshot");
  await picker.getByLabel("Send without previous context").check();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "Completed" }),
  ).toHaveCount(1);
  await expect(
    page.getByRole("button", { name: "Copy response", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", {
      name: "Repeat with selected model",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Edit as a new run", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Compare saved input", exact: true }),
  ).toHaveCount(0);
  expect(await (await page.request.get("/api/conversations")).json()).toEqual(
    before,
  );
  expect(requests).not.toContain("/api/attachments");
  expect(requests).not.toContain("/api/runs");
  expect(requests).not.toContain("/api/conversations");
  expect(
    await page.evaluate(() => localStorage.length + sessionStorage.length),
  ).toBe(0);
  await page.screenshot({
    path: `../artifacts/temporary-${info.project.name}.png`,
    fullPage: true,
  });
  page.once("dialog", (dialog) => dialog.dismiss());
  await page
    .getByRole("button", { name: "End temporary chat", exact: true })
    .click();
  await expect(
    page.getByText("Temporary · Not saved", { exact: true }),
  ).toBeVisible();
  page.once("dialog", (dialog) => dialog.accept());
  await page
    .getByRole("button", { name: "End temporary chat", exact: true })
    .click();
  await expect(
    page.getByText("Temporary · Not saved", { exact: true }),
  ).toHaveCount(0);
  await expect(page.getByLabel("Message", { exact: true })).toHaveValue("");
  expect((await page.request.get(`/api/conversations/${id}`)).status()).toBe(
    404,
  );
  expect(
    (await page.request.get(`/api/attachments/tmp_${id}_unknown`)).status(),
  ).toBe(410);
  await page
    .getByLabel("Message", { exact: true })
    .fill(`Ordinary chat after temporary ${info.project.name}`);
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "Completed" }),
  ).toHaveCount(1);
  expect(
    (await (await page.request.get("/api/conversations")).json()).length,
  ).toBe(before.length + 1);
});

test("reload discards temporary contents and mode changes require explicit dismissal", async ({
  page,
}, info) => {
  await signIn(page);
  let id = await begin(page);
  await page
    .getByLabel("Message", { exact: true })
    .fill("Private draft that must disappear on reload");
  page.once("dialog", (dialog) => dialog.accept());
  await page.reload();
  await expect(page.getByLabel("Message", { exact: true })).toHaveValue("");
  await expect(
    page.getByText("Temporary · Not saved", { exact: true }),
  ).toHaveCount(0);
  await expect
    .poll(async () =>
      (await page.request.get(`/api/attachments/tmp_${id}_unknown`)).status(),
    )
    .toBe(410);
  id = await begin(page);
  await page
    .getByLabel("Message", { exact: true })
    .fill("Do not silently move this into Compare");
  page.once("dialog", (dialog) => dialog.dismiss());
  await page.getByLabel("Mode", { exact: true }).selectOption("compare");
  await expect(page.getByLabel("Mode", { exact: true })).toHaveValue("chat");
  await expect(page.getByLabel("Message", { exact: true })).toHaveValue(
    "Do not silently move this into Compare",
  );
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByLabel("Mode", { exact: true }).selectOption("compare");
  await expect(page.getByLabel("Mode", { exact: true })).toHaveValue("compare");
  await expect(
    page.getByText("Temporary · Not saved", { exact: true }),
  ).toHaveCount(0);
  expect(
    (await page.request.get(`/api/attachments/tmp_${id}_unknown`)).status(),
  ).toBe(410);
  await page.getByLabel("Mode", { exact: true }).selectOption("chat");
  await expect(page.getByLabel("Message", { exact: true })).toHaveValue("");
  await page.setViewportSize({ width: 360, height: 430 });
  await begin(page);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await expect(
    page.getByRole("button", { name: "End temporary chat", exact: true }),
  ).toBeInViewport();
  await page.screenshot({
    path: `../artifacts/temporary-small-${info.project.name}.png`,
    fullPage: true,
  });
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page.getByLabel("Owner passphrase")).toBeVisible();
});

test("opening saved history discards temporary state even when the history read fails", async ({
  page,
}, info) => {
  await signIn(page);
  const title = `Saved history before temporary ${info.project.name}`;
  await page.getByLabel("Message", { exact: true }).fill(title);
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "Completed" }),
  ).toHaveCount(1);
  const history = await (await page.request.get("/api/conversations")).json();
  const saved = history.find((item: { title: string }) => item.title === title);
  expect(saved).toBeTruthy();
  const id = await begin(page);
  await page
    .getByLabel("Message", { exact: true })
    .fill("Private draft must not escape into saved history");
  await page.route(`**/api/conversations/${saved.id}`, (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({
        error: { message: "Synthetic history read failure" },
      }),
    }),
  );
  await navigation(page);
  page.once("dialog", (dialog) => dialog.accept());
  await page
    .getByRole("navigation", { name: "Search history" })
    .getByRole("button", { name: title, exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Close navigation", exact: true }),
  ).toBeHidden();
  await expect(
    page.getByText("Temporary · Not saved", { exact: true }),
  ).toHaveCount(0);
  await expect(page.getByLabel("Message", { exact: true })).toHaveValue("");
  await expect(
    page.getByText("Synthetic history read failure", { exact: true }),
  ).toBeVisible();
  expect(
    (await page.request.get(`/api/attachments/tmp_${id}_unknown`)).status(),
  ).toBe(410);
  await page.unroute(`**/api/conversations/${saved.id}`);
  await navigation(page);
  await page
    .getByRole("navigation", { name: "Search history" })
    .getByRole("button", { name: title, exact: true })
    .click();
  await expect(
    page.getByRole("status").filter({ hasText: "Completed" }),
  ).toHaveCount(1);
  await expect(
    page.getByRole("button", { name: "Send message", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByLabel("Attach files to chat", { exact: true }),
  ).toBeEnabled();
});
