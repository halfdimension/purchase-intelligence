export type Phase1SizeListingVariant = {
  active?: boolean | null;
  attributes?: unknown;
  title?: string | null;
};

export function normalizePhase1Size(
  value: string,
) {
  const normalized = value.trim().toUpperCase();

  const match = normalized.match(
    /UK\s*([0-9]+(?:\.[0-9]+)?)/,
  );

  if (match) {
    return `UK ${match[1]}`;
  }

  return normalized;
}

function stringAttribute(
  value: unknown,
  key: string,
) {
  if (
    !value ||
    typeof value !== "object" ||
    Array.isArray(value)
  ) {
    return null;
  }

  const attribute = (
    value as Record<string, unknown>
  )[key];

  return typeof attribute === "string"
    ? attribute
    : null;
}

export function activePhase1VariantsForSize<
  Variant extends Phase1SizeListingVariant,
>(
  variants: readonly Variant[],
  normalizedRequestedSize: string,
) {
  return variants.filter(
    (variant) =>
      variant.active === true &&
      normalizePhase1Size(
        stringAttribute(
          variant.attributes,
          "size",
        ) ??
          variant.title ??
          "",
      ) === normalizedRequestedSize,
  );
}
