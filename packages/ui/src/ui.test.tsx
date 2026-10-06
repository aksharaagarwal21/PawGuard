import { render, screen } from "@testing-library/react";

import { Button, ErrorSummary, Field, StatusChip, TextInput } from "./index";

describe("Field", () => {
  it("links the label, hint and error to the control", () => {
    render(
      <Field id="nick" label="Nickname" hint="Optional" error="Too long">
        {(aria) => <TextInput {...aria} />}
      </Field>,
    );
    const input = screen.getByLabelText("Nickname");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input.getAttribute("aria-describedby")).toBe("nick-hint nick-error");
    expect(screen.getByText("Too long")).toHaveAttribute("id", "nick-error");
  });
});

describe("Button", () => {
  it("is disabled and busy while loading", () => {
    render(<Button loading>Save</Button>);
    const btn = screen.getByRole("button", { name: "Save" });
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute("aria-busy", "true");
  });
});

describe("StatusChip", () => {
  it("renders its text so status is never conveyed by colour alone", () => {
    render(<StatusChip kind="submitted">Submitted for review</StatusChip>);
    expect(screen.getByText("Submitted for review")).toBeVisible();
  });
});

describe("ErrorSummary", () => {
  it("links each error to its field", () => {
    render(<ErrorSummary title="Fix these" errors={[{ fieldId: "date", message: "Enter a date" }]} />);
    expect(screen.getByRole("link", { name: "Enter a date" })).toHaveAttribute("href", "#date");
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });
});
