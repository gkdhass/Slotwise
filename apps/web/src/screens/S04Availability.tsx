import { Shell } from "../components/Shell";
import { Input } from "../components/Input";
import { Button } from "../components/Button";

const days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

export default function S04Availability() {
  return (
    <Shell title="Availability" subtitle="Choose the hours you can meet">
      <div className="flex flex-col gap-4">
        {days.map((d) => (
          <div key={d} className="flex items-center gap-3">
            <span className="w-12 text-small font-medium text-text">{d}</span>
            <Input label={`${d} start`} type="time" />
            <Input label={`${d} end`} type="time" />
          </div>
        ))}
        <Button>Save availability</Button>
      </div>
    </Shell>
  );
}