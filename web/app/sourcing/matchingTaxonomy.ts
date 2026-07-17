export const dismissReasonGroups = [
  {
    label: "Identity / Match",
    reasons: [
      ["wrong_product", "Wrong Product"],
      ["wrong_platform", "Wrong Platform"],
      ["wrong_edition_version", "Wrong Edition / Version"],
      ["non_north_american_version", "Non-North-American Version"],
      ["digital_item", "Digital Item"],
      ["nfr", "NFR"],
    ],
  },
  {
    label: "Completeness",
    reasons: [["incomplete_product", "Incomplete Product"]],
  },
  {
    label: "Packaging / Condition",
    reasons: [
      ["missing_shrink_wrap", "Missing Shrink Wrap"],
      ["suspected_reseal", "Suspected Reseal"],
      ["packaging_damage", "Packaging Damage"],
    ],
  },
  {
    label: "Business / Sourcing",
    reasons: [
      ["roi_too_low", "ROI Too Low"],
      ["sales_velocity_too_low", "Sales Velocity Too Low"],
      ["too_much_competition", "Too Much Competition"],
      ["capital_better_used_elsewhere", "Capital Better Used Elsewhere"],
      ["valid_product_poor_opportunity", "Valid Product, Poor Opportunity"],
    ],
  },
  {
    label: "System",
    reasons: [
      ["no_longer_available", "No Longer Available"],
      ["other", "Other"],
    ],
  },
] as const;
