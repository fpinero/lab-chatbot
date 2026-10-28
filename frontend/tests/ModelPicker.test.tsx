import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import ModelPicker from "../src/features/chat/ModelPicker";

const models = [
  { id: "vendor/compact", name: "Vendor: Compact" },
  {
    id: "nvidia/nemotron-3-ultra:free",
    name: "NVIDIA: Nemotron 3 Ultra (free)",
  },
];

test("name/publisher/ID search is case insensitive and commits only an explicit choice", async () => {
  const selected = vi.fn();
  function Picker() {
    const [value, setValue] = useState(models[0].id);
    return (
      <ModelPicker
        models={models}
        favorites={[]}
        value={value}
        onChange={(id) => {
          setValue(id);
          selected(id);
        }}
      />
    );
  }
  render(<Picker />);
  const input = screen.getByRole("combobox", { name: "Model" });
  expect(input).toHaveValue("Compact");
  await userEvent.click(input);
  await userEvent.type(input, "NeMoTrOn");
  expect(screen.getAllByRole("option")).toHaveLength(1);
  expect(screen.getByRole("option")).toHaveTextContent("NVIDIA");
  expect(selected).not.toHaveBeenCalled();
  await userEvent.keyboard("{Escape}");
  expect(input).toHaveValue("Compact");
  await userEvent.click(input);
  await userEvent.type(input, "NVIDIA/NEMOTRON-3");
  await userEvent.keyboard("{Enter}");
  expect(selected).toHaveBeenCalledExactlyOnceWith(models[1].id);
  expect(input).toHaveValue("Nemotron 3 Ultra (free)");
});

test("arrows and pointer selection work, empty results and Escape never submit a surrounding form", async () => {
  const selected = vi.fn(),
    submit = vi.fn();
  render(
    <form
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <ModelPicker
        models={models}
        favorites={[]}
        value={models[0].id}
        onChange={selected}
      />
    </form>,
  );
  const input = screen.getByRole("combobox", { name: "Model" });
  await userEvent.click(input);
  await userEvent.keyboard("{ArrowDown}{Enter}");
  expect(selected).toHaveBeenLastCalledWith(models[1].id);
  await userEvent.click(input);
  await userEvent.type(input, "not-a-model");
  expect(screen.getByText("No matching models")).toBeVisible();
  await userEvent.keyboard("{Enter}{Escape}");
  expect(submit).not.toHaveBeenCalled();
  expect(selected).toHaveBeenCalledTimes(1);
  await userEvent.click(input);
  await userEvent.type(input, "vendor");
  await userEvent.click(screen.getByRole("option"));
  expect(selected).toHaveBeenLastCalledWith(models[0].id);
});
