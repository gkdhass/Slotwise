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

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/login" replace />} />
      <Route path="/login" element={<S01Auth />} />
      <Route path="/register" element={<S01Auth />} />
      <Route path="/app" element={<S02Dashboard />} />
      <Route path="/app/events/new" element={<S03EventEditor />} />
      <Route path="/app/events/:id/edit" element={<S03EventEditor />} />
      <Route path="/app/events/:id/availability" element={<S04Availability />} />
      <Route path="/app/events/:id/preview" element={<S05PreviewPublish />} />
      <Route path="/app/bookings" element={<S11BookingList />} />
      <Route path="/book/:slug" element={<S06PublicEvent />} />
      <Route path="/book/:slug/slots" element={<S07SlotSelector />} />
      <Route path="/book/:slug/details" element={<S08InviteeDetails />} />
      <Route path="/booking/confirmed/:reference" element={<S09Confirmation />} />
      <Route path="/manage/:token" element={<S10Management />} />
      <Route path="*" element={<div className="p-8 text-text">Not found</div>} />
    </Routes>
  );
}