"use client";

import { useEffect, useRef } from "react";

import { getBackendBaseURL } from "@/core/config";

interface IdentitySeederProps {
  userName: string | null | undefined;
  userEmail: string | null | undefined;
}

/**
 * Seeds the authenticated user's name and email into the DeerFlow memory
 * system on first sign-in. The backend tracks whether seeding has already
 * happened via a flag in memory.json, so:
 *
 * - First login ever: creates name/email facts in memory.
 * - Any subsequent login (same or different browser/device): only updates
 *   existing facts if values changed; deleted facts stay deleted.
 * - After "Clear all memory": seeds fresh facts on next login.
 *
 * sessionStorage prevents redundant HTTP calls within the same browser tab
 * session, but the real guard is server-side.
 */
export function IdentitySeeder({ userName, userEmail }: IdentitySeederProps) {
  const calledRef = useRef(false);

  useEffect(() => {
    if (calledRef.current) return;
    if (!userName && !userEmail) return;

    // Avoid a second call within the same browser tab session.
    const storageKey = "deerflow.identity-seeded";
    if (sessionStorage.getItem(storageKey) === "1") return;

    calledRef.current = true;

    void fetch(`${getBackendBaseURL()}/api/memory/seed-identity`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: userName, email: userEmail }),
    })
      .then((res) => {
        if (res.ok) {
          sessionStorage.setItem(storageKey, "1");
        }
      })
      .catch(() => {
        // Non-critical — will retry on next page load.
        calledRef.current = false;
      });
  }, [userName, userEmail]);

  return null;
}
