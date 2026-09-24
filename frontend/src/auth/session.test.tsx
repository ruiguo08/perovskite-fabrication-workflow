import { render, screen } from "@testing-library/react";
import { ApiError } from "../lib/api";
import { SessionProvider, useSession } from "./session";
import { beforeEach, describe, expect, it, vi } from "vitest";

const apiFetchMock = vi.hoisted(() => vi.fn());

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return { ...actual, apiFetch: apiFetchMock };
});

function SessionStatusProbe() {
  const { status } = useSession();
  return <p>{status}</p>;
}

describe("SessionProvider", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
  });

  it("distinguishes a server failure from an unauthenticated session", async () => {
    apiFetchMock.mockRejectedValue(
      new ApiError(503, "Session service is unavailable"),
    );

    render(
      <SessionProvider>
        <SessionStatusProbe />
      </SessionProvider>,
    );

    expect(await screen.findByText("error")).toBeInTheDocument();
  });
});
