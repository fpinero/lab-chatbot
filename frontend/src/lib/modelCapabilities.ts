import { copy } from "./copy";

export type ModelChoice = {
  id: string;
  name: string;
  input_modalities?: string[];
};

export const supportsTextAndImage = (
  model: Pick<ModelChoice, "input_modalities">,
) =>
  model.input_modalities?.includes("text") === true &&
  model.input_modalities.includes("image");

export function modelInputLabel(model: Pick<ModelChoice, "input_modalities">) {
  if (supportsTextAndImage(model)) return copy.textAndImage;
  if (model.input_modalities?.includes("image")) return copy.imageInput;
  return model.input_modalities?.length
    ? copy.noImageInput
    : copy.inputSupportUnknown;
}

export function filterModelChoices(
  models: ModelChoice[],
  query: string,
  imageOnly: boolean,
  favorites: string[] = [],
) {
  const terms = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  return models
    .filter(
      (model) =>
        (!imageOnly || supportsTextAndImage(model)) &&
        terms.every((term) =>
          `${model.name} ${model.id}`.toLocaleLowerCase().includes(term),
        ),
    )
    .sort(
      (a, b) =>
        Number(favorites.includes(b.id)) - Number(favorites.includes(a.id)),
    );
}
