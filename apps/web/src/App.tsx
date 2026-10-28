import { useEffect, useState, type ReactNode } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import S01Auth from "./screens/S01Auth";
import S02Dashboard from "./screens/S02Dashboard";
import S03EventEditor from "./screens/S03EventEditor";
import S04Availability from "./screens/S04Availability";
import S05PreviewPublish from "./screens/S05PreviewPublish";
import S06PublicEvent from "./screens/S06PublicEvent";
import S07SlotSelector from "./screens/S07SlotSelector";
import S08InviteeDetails from "./screens/S08InviteeDetails";
import S09Confirmation from "./screens/S09Confirmation";
import S10Management from "./screens/S10Management";
import S11BookingList from "./screens/S11BookingList";
import { me } from "./lib/api";

/**
 * Owner screens require a server session. 401 from /auth/me sends the visitor
 * to sign in; any other failure is treated as unauthenticated (fail closed).
 */
function RequireAuth({ children }: { children: ReactNode }) {
  const [state, setState] = useState<"loading" | "ok" | "denied">("loading");

  useEffect(() => {
    let alive = true;
    me()
      .then(() => alive && setState("ok"))
      .catch(() => alive && setState("denied"));
    return () => {
      alive = false;
    };
  }, []);

  if (state === "loading") return <p className="p-8 text-text-muted">Checking your session…</p>;
  if (state === "denied") return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/login" replace />} />
      <Route path="/login" element={<S01Auth />} />
      <Route path="/register" element={<S01Auth />} />
      <Route path="/app" element={<RequireAuth><S02Dashboard /></RequireAuth>} />
      <Route path="/app/events/new" element={<RequireAuth><S03EventEditor /></RequireAuth>} />
      <Route path="/app/events/:id/edit" element={<RequireAuth><S03EventEditor /></RequireAuth>} />
      <Route path="/app/events/:id/availability" element={<RequireAuth><S04Availability /></RequireAuth>} />
      <Route path="/app/events/:id/preview" element={<RequireAuth><S05PreviewPublish /></RequireAuth>} />
      <Route path="/app/bookings" element={<RequireAuth><S11BookingList /></RequireAuth>} />
      <Route path="/book/:slug" element={<S06PublicEvent />} />
      <Route path="/book/:slug/slots" element={<S07SlotSelector />} />
      <Route path="/book/:slug/details" element={<S08InviteeDetails />} />
      <Route path="/booking/confirmed/:reference" element={<S09Confirmation />} />
      <Route path="/manage/:token" element={<S10Management />} />
      <Route path="*" element={<div className="p-8 text-text">Not found</div>} />
    </Routes>
  );
}
