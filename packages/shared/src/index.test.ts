import { describe, it, expect } from "vitest";
import { errorCodes } from "./index";

describe("shared", () => {
  it("exports SLOT_UNAVAILABLE code", () => {
    expect(errorCodes.SLOT_UNAVAILABLE).toBe("SLOT_UNAVAILABLE");
  });
});