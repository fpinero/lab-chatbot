import { act, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, expect, test, vi } from "vitest";
import CatalogRefresh, {
  useCatalogRefresh,
} from "../src/features/chat/CatalogRefresh";
import { ApiError, request } from "../src/lib/api";

afterEach(() => vi.useRealTimers());
const catalog = { fetched_at: 1, refresh_after_seconds: 0 };
const button = () => screen.getByRole("button", { name: "Refresh models" });
function RefreshFixture(props: {
  catalog: typeof catalog;
  refresh: () => Promise<typeof catalog>;
  onRefresh: (value: typeof catalog) => void;
  expired: () => void;
}) {
  const control = useCatalogRefresh(props);
  return <CatalogRefresh control={control} />;
}

test("rebuilding the composer does not restart an expired catalog wait", async () => {
  vi.useFakeTimers();
  const initial = { ...catalog, refresh_after_seconds: 3 };
  function Fixture() {
    const [epoch, setEpoch] = useState(0);
    const control = useCatalogRefresh({
      catalog: initial,
      refresh: vi.fn(),
      onRefresh: vi.fn(),
      expired: vi.fn(),
    });
    return (
      <>
        <button onClick={() => setEpoch((n) => n + 1)}>Reset composer</button>
        <CatalogRefresh key={epoch} control={control} />
      </>
    );
  }
  render(<Fixture />);
  await act(async () => {
    vi.advanceTimersByTime(3000);
  });
  expect(button()).toBeEnabled();
  fireEvent.click(screen.getByRole("button", { name: "Reset composer" }));
  expect(button()).toBeEnabled();
});

test("rebuilding the composer preserves an in-flight refresh and its result", async () => {
  let complete!: (value: typeof catalog) => void;
  const onRefresh = vi.fn();
  const refresh = vi.fn(
    () =>
      new Promise<typeof catalog>((resolve) => {
        complete = resolve;
      }),
  );
  function Fixture() {
    const [epoch, setEpoch] = useState(0);
    const control = useCatalogRefresh({
      catalog,
      refresh,
      onRefresh,
      expired: vi.fn(),
    });
    return (
      <>
        <button onClick={() => setEpoch((n) => n + 1)}>Reset composer</button>
        <CatalogRefresh key={epoch} control={control} />
      </>
    );
  }
  render(<Fixture />);
  fireEvent.click(button());
  fireEvent.click(screen.getByRole("button", { name: "Reset composer" }));
  expect(button()).toHaveTextContent("Refreshing models...");
  expect(button()).toBeDisabled();
  await act(async () => {
    complete({ ...catalog, fetched_at: 2 });
  });
  expect(refresh).toHaveBeenCalledOnce();
  expect(onRefresh).toHaveBeenCalledOnce();
  expect(screen.getByRole("status")).toHaveTextContent("Models refreshed.");
});

test("server cooldown disables refresh until the actual wait expires", async () => {
  vi.useFakeTimers();
  const refresh = vi.fn();
  render(
    <RefreshFixture
      catalog={{ ...catalog, refresh_after_seconds: 3 }}
      refresh={refresh}
      onRefresh={vi.fn()}
      expired={vi.fn()}
    />,
  );
  expect(button()).toBeDisabled();
  expect(button()).toHaveAccessibleDescription("Refresh in 3s");
  fireEvent.click(button());
  expect(refresh).not.toHaveBeenCalled();
  await act(async () => {
    vi.advanceTimersByTime(3000);
  });
  expect(button()).toBeEnabled();
});

test("Retry-After is honored and successful retry removes rate-limit feedback", async () => {
  vi.useFakeTimers();
  const fetcher = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({ error: { message: "Synthetic rate limit" } }),
        { status: 429, headers: { "Retry-After": "3" } },
      ),
    )
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({ ...catalog, fetched_at: 2, refresh_after_seconds: 2 }),
      ),
    );
  const onRefresh = vi.fn();
  render(
    <RefreshFixture
      catalog={catalog}
      refresh={() => request<typeof catalog>("/models/refresh", "POST")}
      onRefresh={onRefresh}
      expired={vi.fn()}
    />,
  );
  await act(async () => {
    fireEvent.click(button());
  });
  expect(button()).toHaveTextContent("Refresh in 3s");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent("refreshed recently");
  await act(async () => {
    vi.advanceTimersByTime(3000);
  });
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
  await act(async () => {
    fireEvent.click(button());
  });
  expect(fetcher).toHaveBeenCalledTimes(2);
  expect(onRefresh).toHaveBeenCalledWith({
    ...catalog,
    fetched_at: 2,
    refresh_after_seconds: 2,
  });
  expect(screen.getByRole("status")).toHaveTextContent("Models refreshed.");
  expect(button()).toBeDisabled();
});

test("failed refresh keeps the saved catalog and clears its error when retry starts", async () => {
  vi.useFakeTimers();
  let complete!: (value: typeof catalog) => void;
  const refresh = vi
    .fn()
    .mockRejectedValueOnce(new ApiError(503, "Synthetic provider failure", 2))
    .mockImplementationOnce(
      () =>
        new Promise<typeof catalog>((resolve) => {
          complete = resolve;
        }),
    );
  const onRefresh = vi.fn();
  render(
    <RefreshFixture
      catalog={catalog}
      refresh={refresh}
      onRefresh={onRefresh}
      expired={vi.fn()}
    />,
  );
  await act(async () => {
    fireEvent.click(button());
  });
  expect(onRefresh).not.toHaveBeenCalled();
  expect(screen.getByRole("alert")).toHaveTextContent(
    "Synthetic provider failure",
  );
  await act(async () => {
    vi.advanceTimersByTime(2000);
  });
  expect(button()).toBeEnabled();
  await act(async () => {
    fireEvent.click(button());
  });
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(button()).toHaveTextContent("Refreshing models...");
  fireEvent.click(button());
  expect(refresh).toHaveBeenCalledTimes(2);
  await act(async () => {
    complete({ ...catalog, fetched_at: 2 });
  });
  expect(screen.getByRole("status")).toHaveTextContent("Models refreshed.");
});

test("expired sessions are handled without overwriting catalog state", async () => {
  const expired = vi.fn(),
    onRefresh = vi.fn();
  render(
    <RefreshFixture
      catalog={catalog}
      refresh={vi.fn().mockRejectedValue(new ApiError(401))}
      onRefresh={onRefresh}
      expired={expired}
    />,
  );
  await act(async () => {
    fireEvent.click(button());
  });
  expect(expired).toHaveBeenCalledOnce();
  expect(onRefresh).not.toHaveBeenCalled();
});

test("unmounted refresh results cannot change another workspace", async () => {
  let complete!: (value: typeof catalog) => void;
  const onRefresh = vi.fn();
  const view = render(
    <RefreshFixture
      catalog={catalog}
      refresh={() =>
        new Promise((resolve) => {
          complete = resolve;
        })
      }
      onRefresh={onRefresh}
      expired={vi.fn()}
    />,
  );
  fireEvent.click(button());
  view.unmount();
  await act(async () => {
    complete(catalog);
  });
  expect(onRefresh).not.toHaveBeenCalled();
});
