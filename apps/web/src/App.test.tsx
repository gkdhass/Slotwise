import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import App from "./App";

// Unit tests never touch the network: the API module is mocked. The real
// end-to-end coverage runs in Playwright against the live API + database.
vi.mock("./lib/api", () => {
  const event = {
    id: "ev-1",
    title: "Intro tutoring",
    slug: "intro-tutoring",
    description: "A 30-minute intro session.",
    durationMinutes: 30,
    locationType: "online",
    locationDetails: "Video link",
    timezone: "Asia/Kolkata",
    isPublished: true,
    archived: false,
  };
  return {
    ApiError: class ApiError extends Error {},
    me: vi.fn(async () => ({ id: "u1", email: "owner@example.test", role: "owner", emailVerified: true })),
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
    listEventTypes: vi.fn(async () => [event]),
    getEventType: vi.fn(async () => event),
    getEventTypeBySlug: vi.fn(async () => event),
    createEventType: vi.fn(async () => event),
    updateEventType: vi.fn(async () => event),
    publishEventType: vi.fn(async () => event),
    archiveEventType: vi.fn(),
    getAvailability: vi.fn(async () => []),
    setAvailability: vi.fn(async () => []),
    getSlots: vi.fn(async () => [
      { startAt: "2026-11-02T04:30:00.000Z", endAt: "2026-11-02T05:00:00.000Z", label: "Mon 2 Nov, 10:00 am" },
    ]),
    createBooking: vi.fn(),
    getBookingByReference: vi.fn(async () => null),
    getBookingByToken: vi.fn(async () => null),
    cancelBooking: vi.fn(),
    rescheduleBooking: vi.fn(),
    listBookings: vi.fn(async () => []),
  };
});

describe("App routes", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the login route without crashing", () => {
    render(
      <MemoryRouter initialEntries={["/login"]}>
        <App />
      </MemoryRouter>,
    );
    expect(screen.getByRole("heading", { name: /sign in/i })).toBeInTheDocument();
  });

  it("renders the dashboard for an authenticated owner", async () => {
    render(
      <MemoryRouter initialEntries={["/app"]}>
        <App />
      </MemoryRouter>,
    );
    expect(await screen.findByRole("heading", { name: /dashboard/i })).toBeInTheDocument();
  });

  it("renders a public event route", async () => {
    render(
      <MemoryRouter initialEntries={["/book/intro-tutoring"]}>
        <App />
      </MemoryRouter>,
    );
    expect(await screen.findByRole("heading", { name: /intro tutoring/i })).toBeInTheDocument();
  });

  it("shows the cancellation policy on the public event page", async () => {
    render(
      <MemoryRouter initialEntries={["/book/intro-tutoring"]}>
        <App />
      </MemoryRouter>,
    );
    expect(await screen.findByTestId("policy-public")).toBeInTheDocument();
  });

  it("renders every route with a heading once loaded", async () => {
    const routes = [
      "/login",
      "/register",
      "/app",
      "/app/events/new",
      "/app/events/1/edit",
      "/app/events/1/availability",
      "/app/events/1/preview",
      "/app/bookings",
      "/book/intro-tutoring",
      "/book/intro-tutoring/slots",
      "/book/intro-tutoring/details",
      "/booking/confirmed/ref-1",
      "/manage/token-1",
    ];
    for (const r of routes) {
      const { unmount } = render(
        <MemoryRouter initialEntries={[r]}>
          <App />
        </MemoryRouter>,
      );
      // Screens load from the API, so each one settles into a state that still
      // exposes a heading (content, empty, error or not-found) — never a
      // heading-less blank page.
      expect((await screen.findAllByRole("heading")).length, `no heading on ${r}`).toBeGreaterThan(0);
      unmount();
    }
  });
});
