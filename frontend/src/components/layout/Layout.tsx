import type { ReactNode } from "react";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

export function Layout({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="flex h-screen bg-base-950">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <Topbar title={title} />
        <main className="flex-1 overflow-y-auto p-6">{children}</main>
      </div>
    </div>
  );
}
