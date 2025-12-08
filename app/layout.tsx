import type { Metadata } from 'next'
import "./globals.css";

export const metadata: Metadata = {
  title: 'VRoom',
  description: 'Temukan mobil impianmu',
}

// app/layout.tsx

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    // TAMBAHKAN suppressHydrationWarning DI SINI:
    <html lang="id" suppressHydrationWarning>
      <body>{children}</body>
    </html>
  );
}