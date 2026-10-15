import type { Metadata } from "next";
import "./globals.css";
import { Nav } from "@/components/Nav";
import { ChatPanel } from "@/components/chat/ChatPanel";

export const metadata: Metadata = {
  title: "beatcut",
  description: "Phone clips + a sound → a finished TikTok, with Claude in the loop.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <Nav />
        <main className="max-w-[1180px] mx-auto px-4 pt-4 pb-24">{children}</main>
        <ChatPanel />
      </body>
    </html>
  );
}
