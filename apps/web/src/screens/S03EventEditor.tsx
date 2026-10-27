import { Shell } from "../components/Shell";
import { Input } from "../components/Input";
import { Button } from "../components/Button";

export default function S03EventEditor() {
  return (
    <Shell title="Event editor" subtitle="Configure your session">
      <form className="flex flex-col gap-4" onSubmit={(e) => e.preventDefault()}>
        <Input label="What should this session be called?" placeholder="Intro tutoring" />
        <Input label="How long should the session last? (minutes)" type="number" placeholder="30" />
        <Input label="Location type" placeholder="online" />
        <Input label="Time zone" placeholder="Asia/Kolkata" />
        <div className="flex gap-2">
          <Button type="submit">Save</Button>
          <Button variant="secondary">Cancel</Button>
        </div>
      </form>
    </Shell>
  );
}