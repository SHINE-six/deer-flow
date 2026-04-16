import { NextResponse } from "next/server";

import { auth } from "@/server/better-auth";

/**
 * Nginx auth_request subrequest endpoint.
 * Returns 200 if the request carries a valid session cookie, 401 otherwise.
 * This is called internally by nginx before proxying protected API routes.
 */
export async function GET(request: Request) {
  const session = await auth.api.getSession({
    headers: request.headers,
  });

  if (!session) {
    return new NextResponse(null, { status: 401 });
  }

  const response = new NextResponse(null, { status: 200 });
  response.headers.set("X-Auth-User-Id", session.user.id);
  return response;
}
