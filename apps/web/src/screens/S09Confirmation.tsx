import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Shell } from "../components/Shell";
import { Button } from "../components/Button";
import { Alert } from "../components/Alert";
import { getBookingByReference } from "../lib/mockApi";
import type { Booking } from "../lib/types";

export default function S09Confirmation() {
  const { reference } = useParams();
  const navigate = useNavigate();
  const [booking, setBooking] = useState<Booking | null>(null);

  useEffect(() => {
    if (!reference) return;
    getBookingByReference(reference).then(setBooking);
  }, [reference]);

  if (!booking) return <Shell title="Loading…" subtitle="Confirming your appointment…" />;

  return (
    <Shell title="Your appointment is confirmed" subtitle={`Booking reference: ${booking.reference}`}>
      <div className="flex flex-col gap-4">
        <Alert variant="success">Your appointment is confirmed.</Alert>
        <p className="text-body text-text">{booking.eventTitle}</p>
        <p className="text-body text-text">
          {new Date(booking.startAt).toLocaleString(undefined, { timeZone: booking.displayTimezone })}{" "}
          {booking.displayTimezone}
        </p>
        <p className="text-small text-text-muted">
          {Math.round((new Date(booking.endAt).getTime() - new Date(booking.startAt).getTime()) / 60000)} minutes
        </p>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={() => navigate(`/manage/${booking.managementToken}`)}>
            Manage booking
          </Button>
        </div>
      </div>
    </Shell>
  );
}