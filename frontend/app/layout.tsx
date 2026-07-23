import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "BTC Arbitrage Dashboard | IBO0OK",
  description: "Real-time Bitcoin arbitrage detection between Polymarket and Kalshi. Contact: IBO0OK",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
