import { useParams, useNavigate, useLocation } from "react-router-dom";
import { Shell } from "../components/Shell";
import { Button } from "../components/Button";
import { Alert } from "../components/Alert";
import type { Booking } from "../lib/types";

export default function S09Confirmation() {
  const { reference } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  // The booking object only exists after the API returned 201/200. A direct
  // visit (or a refresh) therefore never claims that a booking succeeded.
  const booking = ((location.state as { booking?: Booking } | null)?.booking ?? null) as Booking | null;

  if (!booking) {
    return (
      <Shell title="Booking confirmation" subtitle={`Reference: ${reference}`}>
        <div className="flex flex-col gap-4">
          <Alert variant="info">
            We can only show booking details in the session where the booking was made. Open the link from your
            confirmation email to view or change this booking.
          </Alert>
          <Button variant="secondary" onClick={() => navigate("/")}>
            Back to start
          </Button>
        </div>
      </Shell>
    );
  }

  const inviteeTz = booking.displayTimezone;
  const hostTz = booking.hostTimezone;

  return (
    <Shell title="Your appointment is confirmed" subtitle={`Booking reference: ${booking.reference}`}>
      <div className="flex flex-col gap-4">
        <Alert variant="success">Your appointment is confirmed.</Alert>
        <p className="text-body text-text">{booking.eventTitle}</p>
        <div>
          <p className="text-body text-text">
            {new Date(booking.startAt).toLocaleString(undefined, { timeZone: inviteeTz, dateStyle: "full", timeStyle: "short" })}
          </p>
          <p className="text-small text-text-muted">Your time zone: {inviteeTz}</p>
          {hostTz && hostTz !== inviteeTz && (
            <p className="text-small text-text-muted">
              Host time zone:{" "}
              {new Date(booking.startAt).toLocaleString(undefined, { timeZone: hostTz, dateStyle: "full", timeStyle: "short" })} ({hostTz})
            </p>
          )}
        </div>
        <p className="text-small text-text-muted">
          {Math.round((new Date(booking.endAt).getTime() - new Date(booking.startAt).getTime()) / 60000)} minutes
        </p>
        <p className="text-small text-text-muted">A confirmation email with a secure management link is on its way.</p>
        {booking.managementToken && (
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => navigate(`/manage/${booking.managementToken}`)}>
              Manage booking
            </Button>
          </div>
        )}
      </div>
    </Shell>
  );
}
