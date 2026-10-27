import { Shell } from "../components/Shell";
import { Input } from "../components/Input";
import { Button } from "../components/Button";
import { Alert } from "../components/Alert";

export default function S08InviteeDetails() {
  return (
    <Shell title="Your details" subtitle="Almost done — confirm your appointment">
      <form className="flex flex-col gap-4" onSubmit={(e) => e.preventDefault()}>
        <Input label="Name" placeholder="Alex Example" />
        <Input label="Email" type="email" placeholder="alex@example.test" />
        <Input label="Note (optional)" placeholder="Anything to share?" />
        <Alert variant="info">Confirming your appointment…</Alert>
        <Button type="submit">Confirm booking</Button>
      </form>
    </Shell>
  );
}