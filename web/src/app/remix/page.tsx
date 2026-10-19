import { RemixUpload } from "@/components/RemixUpload";
import { projects } from "@/lib/beatcut";

export const dynamic = "force-dynamic";

/** Remix: a finished video in, four new posts out. */
export default async function Remix() {
  const ps = (await projects()).filter((p) => p.rendered);
  return (
    <div>
      <h1>Remix</h1>
      <p className="lede">A reel that did numbers is footage. Drop it in and get four new posts from the same shots: a short hook cut, the same story on another sound, a reorder, a long version. Each one lands in the feed like any other video, with the edit buttons and the post step.</p>
      <RemixUpload videos={ps} />
    </div>
  );
}
