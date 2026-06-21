import { NextResponse } from "next/server";

export const runtime = "nodejs";

const DEFAULT_COGNITO_DOMAIN = "https://us-west-2ibxxtq9xl.auth.us-west-2.amazoncognito.com";
const DEFAULT_CLIENT_ID = "4008ukjg31rsj9gqn59fhk2nkr";
const DEFAULT_LOGOUT_URI = "https://mbop.midnightblueenterprises.com/";

export async function GET() {
  const cognitoDomain = process.env.COGNITO_LOGOUT_DOMAIN || DEFAULT_COGNITO_DOMAIN;
  const clientId = process.env.COGNITO_CLIENT_ID || DEFAULT_CLIENT_ID;
  const logoutUri = process.env.COGNITO_LOGOUT_URI || DEFAULT_LOGOUT_URI;
  const logoutUrl = new URL("/logout", cognitoDomain);

  logoutUrl.searchParams.set("client_id", clientId);
  logoutUrl.searchParams.set("logout_uri", logoutUri);

  const response = NextResponse.redirect(logoutUrl);
  const expired = {
    expires: new Date(0),
    maxAge: 0,
    path: "/",
  };

  response.cookies.set("AWSELBAuthSessionCookie", "", expired);
  for (let index = 0; index < 4; index += 1) {
    response.cookies.set(`AWSELBAuthSessionCookie-${index}`, "", expired);
  }

  return response;
}
