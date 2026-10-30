import { useEffect, useState } from "react";
import { Download, Share, SquarePlus, X } from "lucide-react";
import {
  getDeferredPrompt,
  installMode,
  isIos,
  isStandalone,
  onInstallPromptChange,
  promptInstall,
} from "../services/installPrompt.js";

/** Customer "Get the app" button. Hidden when the app is already installed. */
export default function GetAppButton({ businessName = "this shop" }) {
  const [hasPrompt, setHasPrompt] = useState(() => Boolean(getDeferredPrompt()));
  const [standalone, setStandalone] = useState(() => isStandalone());
  const [showIosHelp, setShowIosHelp] = useState(false);
  useEffect(() => onInstallPromptChange((event) => {
    setHasPrompt(Boolean(event));
    setStandalone(isStandalone());
  }), []);

  const mode = installMode({ standalone, ios: isIos(), hasPrompt });
  if (mode === "hidden") return null;

  async function handleClick() {
    if (mode === "prompt") {
      const outcome = await promptInstall();
      if (outcome === "accepted") setStandalone(true);
      return;
    }
    setShowIosHelp(true);
  }

  return <div className="get-app">
    <button className="get-app-button" type="button" onClick={handleClick}>
      <Download size={18} aria-hidden="true" /> Get the app
    </button>
    {showIosHelp ? <div className="get-app-ios-help" role="dialog" aria-modal="false" aria-labelledby="get-app-ios-title">
      <button className="get-app-close" type="button" aria-label="Close" onClick={() => setShowIosHelp(false)}><X size={18} /></button>
      <h2 id="get-app-ios-title">Add {businessName} to your Home Screen</h2>
      <ol>
        <li><Share size={18} aria-hidden="true" /> Tap the <strong>Share</strong> button in Safari’s toolbar.</li>
        <li><SquarePlus size={18} aria-hidden="true" /> Scroll down and tap <strong>Add to Home Screen</strong>, then <strong>Add</strong>.</li>
      </ol>
    </div> : null}
  </div>;
}
