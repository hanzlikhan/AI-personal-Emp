import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Silver Tier AI — Dashboard",
  description: "Real-time control center for Silver Tier AI Employee",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-background font-sans antialiased" suppressHydrationWarning>
        {children}
      </body>
    </html>
  );
}
