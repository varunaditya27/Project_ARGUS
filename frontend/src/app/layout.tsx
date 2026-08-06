import type { Metadata } from "next";
import { DM_Serif_Display } from "next/font/google";
import "./globals.css";
import { DashboardLayout } from "@/layouts/dashboard-layout";

const dmSerifDisplay = DM_Serif_Display({
  subsets: ["latin"],
  weight: ["400"],
  variable: "--font-display",
  display: "swap",
});

export const metadata: Metadata = {
  title: "ARGUS — Attendance Recognition System",
  description: "AI-powered masked face recognition attendance management for academic institutions.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={dmSerifDisplay.variable}>
      <body>
        <DashboardLayout>{children}</DashboardLayout>
      </body>
    </html>
  );
}
