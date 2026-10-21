import { NextRequest, NextResponse } from 'next/server';
export function middleware(request: NextRequest) {
  if (process.env.REQUIRE_SITE_AUTH !== 'true' || request.nextUrl.pathname === '/api/health') return NextResponse.next();
  const password = process.env.SITE_PASSWORD;
  const username = process.env.SITE_USER || 'owner';
  if (!password) return new NextResponse('Inloggning är inte konfigurerad.', {status:503});
  const header = request.headers.get('authorization') || '';
  if (header.startsWith('Basic ')) {
    try {
      const decoded = atob(header.slice(6));
      const separator = decoded.indexOf(':');
      if (decoded.slice(0, separator) === username && decoded.slice(separator + 1) === password) return NextResponse.next();
    } catch { /* invalid credentials receive the same challenge */ }
  }
  return new NextResponse('Logga in för att använda Fotbolls-AI.', {status:401,headers:{'WWW-Authenticate':'Basic realm="Fotbolls-AI", charset="UTF-8"','Cache-Control':'no-store'}});
}
export const config = { matcher: '/:path*' };
