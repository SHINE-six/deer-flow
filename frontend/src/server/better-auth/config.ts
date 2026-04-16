import { betterAuth } from "better-auth";
import { admin, username } from "better-auth/plugins";
import { Pool } from "pg";

const pool = new Pool({
  connectionString:
    process.env.AUTH_DATABASE_URL ??
    "postgresql://lightrag:changeme@localhost:5432/auth",
});

const baseURL = process.env.BETTER_AUTH_URL ?? "http://localhost:3000";
const isProduction = baseURL.includes("aidebate.site");

export const auth = betterAuth({
  database: pool,
  emailAndPassword: {
    enabled: true,
  },
  plugins: [username(), admin()],
  ...(isProduction && {
    trustedOrigins: [
      "https://www.aidebate.site",
      "https://admin.aidebate.site",
    ],
    advanced: {
      crossSubDomainCookies: {
        enabled: true,
        domain: ".aidebate.site",
      },
    },
  }),
});

export type Session = typeof auth.$Infer.Session;
