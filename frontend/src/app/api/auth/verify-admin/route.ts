import { NextResponse } from "next/server";

import { auth } from "@/server/better-auth";

/**
 * Nginx auth_request subrequest endpoint for admin.aidebate.site.
 * Returns 200 if the request carries a valid session cookie AND the user has admin role.
 * Returns 401 if no valid session (nginx redirects to login).
 * Returns 403 if authenticated but not an admin (nginx shows forbidden page).
 */
export async function GET(request: Request) {
  const session = await auth.api.getSession({
    headers: request.headers,
  });

  if (!session) {
    return new NextResponse(null, { status: 401 });
  }

  if (session.user.role !== "admin") {
    return new NextResponse(null, { status: 403 });
  }

  return new NextResponse(null, { status: 200 });
}
