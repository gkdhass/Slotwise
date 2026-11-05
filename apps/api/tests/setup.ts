import { beforeEach } from "vitest";
import { resetRateLimits } from "../src/middleware/rateLimit.js";

beforeEach(() => {
  resetRateLimits();
});
