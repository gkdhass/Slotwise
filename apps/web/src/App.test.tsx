import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import App from "./App";

describe("App routes (M0)", () => {
  it("renders the login route without crashing", () => {
    render(
      <MemoryRouter initialEntries={["/login"]}>
        <App />
      </MemoryRouter>,
    );
    expect(screen.getByRole("heading", { name: /sign in/i })).toBeInTheDocument();
  });

  it("renders the dashboard route", () => {
    render(
      <MemoryRouter initialEntries={["/app"]}>
        <App />
      </MemoryRouter>,
    );
    expect(screen.getByRole("heading", { name: /dashboard/i })).toBeInTheDocument();
  });

  it("renders a public event route", async () => {
    render(
      <MemoryRouter initialEntries={["/book/intro-tutoring"]}>
        <App />
      </MemoryRouter>,
    );
    expect(await screen.findByRole("heading", { name: /intro tutoring/i })).toBeInTheDocument();
  });

  it("renders every M0 route without crashing", () => {
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
      expect(screen.getAllByRole("heading").length).toBeGreaterThan(0);
      unmount();
    }
  });
});