import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata = { title: 'Fotbolls-AI · Football intelligence', description: 'Verifierbar fotbollsanalys och virtuell modellutvärdering.' };
export default function Layout({children}:{children:React.ReactNode}) { return <html lang="sv"><body>{children}</body></html> }
