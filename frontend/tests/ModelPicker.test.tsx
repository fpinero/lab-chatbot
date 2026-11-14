import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import ModelPicker from "../src/features/chat/ModelPicker";
import type { ModelChoice } from "../src/lib/modelCapabilities";

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
        imageOnly={false}
        onImageOnlyChange={vi.fn()}
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
        imageOnly={false}
        onImageOnlyChange={vi.fn()}
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

const capabilityModels: ModelChoice[] = [
  {
    id: "vendor/text",
    name: "Vendor: Vision in name only",
    input_modalities: ["text"],
  },
  {
    id: "vendor/vision-one",
    name: "Vendor: Vision One",
    input_modalities: ["text", "image"],
  },
  { id: "vendor/unknown", name: "Vendor: Unknown" },
  {
    id: "vendor/image-only",
    name: "Vendor: Image input only",
    input_modalities: ["image"],
  },
  {
    id: "vendor/vision-two",
    name: "Vendor: Vision Two",
    input_modalities: ["image", "text"],
  },
];

function FilterPicker({
  choices = capabilityModels,
  selected = vi.fn(),
  submit = vi.fn(),
}: {
  choices?: ModelChoice[];
  selected?: (id: string) => void;
  submit?: () => void;
}) {
  const [imageOnly, setImageOnly] = useState(false);
  const [value, setValue] = useState(capabilityModels[0].id);
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <ModelPicker
        models={choices}
        value={value}
        favorites={["vendor/vision-two"]}
        imageOnly={imageOnly}
        onImageOnlyChange={setImageOnly}
        onChange={(id) => {
          setValue(id);
          selected(id);
        }}
      />
    </form>
  );
}

test("image filtering uses declared text/image inputs, retains favorites and never chooses a replacement", async () => {
  const selected = vi.fn();
  render(<FilterPicker selected={selected} />);
  const input = screen.getByRole("combobox", { name: "Model" });
  await userEvent.click(input);
  expect(screen.getAllByRole("option")).toHaveLength(5);
  expect(screen.getByRole("option", { name: /Unknown/ })).toHaveTextContent(
    "Input support unavailable",
  );
  await userEvent.click(
    screen.getByRole("checkbox", { name: "Only models that accept images" }),
  );
  const options = screen.getAllByRole("option");
  expect(options).toHaveLength(2);
  expect(options[0]).toHaveTextContent("Vision Two");
  expect(options[1]).toHaveTextContent("Vision One");
  expect(
    options.every((option) => option.textContent!.includes("Text + image")),
  ).toBe(true);
  expect(
    screen.getByText(/current model is outside this filter/),
  ).toBeVisible();
  expect(selected).not.toHaveBeenCalled();
  await userEvent.click(input);
  await userEvent.type(input, "VENDOR VISION-ONE");
  expect(screen.getAllByRole("option")).toHaveLength(1);
  await userEvent.clear(input);
  await userEvent.type(input, "no-match");
  expect(
    screen.getByText("No Text + image models match this search"),
  ).toBeVisible();
  await userEvent.clear(input);
  await userEvent.click(
    screen.getByRole("checkbox", { name: "Only models that accept images" }),
  );
  expect(screen.getAllByRole("option")).toHaveLength(5);
  await userEvent.keyboard("{Escape}");
  expect(input).toHaveValue("Vision in name only");
  expect(selected).not.toHaveBeenCalled();
});

test("filter keyboard controls do not submit and ArrowUp from closed chooses the final compatible option", async () => {
  const selected = vi.fn(),
    submit = vi.fn();
  render(<FilterPicker selected={selected} submit={submit} />);
  const input = screen.getByRole("combobox", { name: "Model" });
  await userEvent.click(input);
  const checkbox = screen.getByRole("checkbox", {
    name: "Only models that accept images",
  });
  await userEvent.tab();
  expect(checkbox).toHaveFocus();
  await userEvent.keyboard(" {Enter}{Escape}");
  expect(submit).not.toHaveBeenCalled();
  expect(input).toHaveFocus();
  expect(input).toHaveAttribute("aria-expanded", "false");
  await userEvent.keyboard("{ArrowUp}{Enter}");
  expect(selected).toHaveBeenCalledExactlyOnceWith("vendor/vision-one");
});

test("catalog capability changes and an empty filtered list stay recoverable without changing selection", async () => {
  const selected = vi.fn();
  const { rerender } = render(<FilterPicker selected={selected} />);
  const input = screen.getByRole("combobox", { name: "Model" });
  await userEvent.click(input);
  await userEvent.click(
    screen.getByRole("checkbox", { name: "Only models that accept images" }),
  );
  rerender(
    <FilterPicker
      selected={selected}
      choices={capabilityModels.map((model) => ({
        ...model,
        input_modalities: [],
      }))}
    />,
  );
  expect(screen.queryAllByRole("option")).toHaveLength(0);
  expect(input).toBeEnabled();
  expect(
    screen.getByText("No Text + image models match this search"),
  ).toBeVisible();
  await userEvent.click(
    screen.getByRole("checkbox", { name: "Only models that accept images" }),
  );
  expect(screen.getAllByRole("option")).toHaveLength(5);
  expect(selected).not.toHaveBeenCalled();
});
