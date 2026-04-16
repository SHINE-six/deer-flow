import { type NextRequest, NextResponse } from "next/server";

export function middleware(request: NextRequest) {
  // Lightweight guard: check if the session cookie exists.
  // Full session validation happens server-side in the workspace layout.
  const sessionToken =
    request.cookies.get("better-auth.session_token")?.value ??
    request.cookies.get("__Secure-better-auth.session_token")?.value;

  if (!sessionToken) {
    const loginUrl = new URL("/auth/login", request.url);
    loginUrl.searchParams.set("callbackUrl", request.nextUrl.pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    // Protect workspace and all sub-routes
    "/workspace/:path*",
  ],
};
