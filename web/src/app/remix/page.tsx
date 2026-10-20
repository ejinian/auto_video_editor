import { RemixUpload } from "@/components/RemixUpload";
import { projects } from "@/lib/beatcut";

export const dynamic = "force-dynamic";

/** Remix: a posted video in, three framings of it out (or four re-cuts of raw footage). */
export default async function Remix() {
  // cut videos only: a reformat keeps its source's cut and has no clips to re-cut
  const ps = (await projects()).filter((p) => p.rendered && !p.reformat);
  return (
    <div>
      <h1>Remix</h1>
      <p className="lede">A reel that did numbers deserves a second run. Paste its link or drop the file and it comes back as three posts with the same cut and a new framing: a hook line on screen, a narration in your voice, a reply to one of the post&apos;s real comments, plus goofy and cinematic versions — Claude writes the copy and picks the moments. Each lands in the feed like any other video, with the post step. Raw footage can be re-cut instead.</p>
      <RemixUpload videos={ps} />
    </div>
  );
}
