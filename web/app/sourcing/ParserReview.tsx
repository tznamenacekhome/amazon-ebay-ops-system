import type { MatchingFeedback } from "../api/sourcing/matchingFeedback";

export function ParserReview({ parserAssessment, sourceAccuracy, setParserAssessment, setSourceAccuracy }: {
  parserAssessment: MatchingFeedback["parserAssessment"]; sourceAccuracy: MatchingFeedback["sourceAccuracy"];
  setParserAssessment: (value: MatchingFeedback["parserAssessment"]) => void;
  setSourceAccuracy: (value: MatchingFeedback["sourceAccuracy"]) => void;
}) {
  return <>
            <fieldset className="text-sm">
              <legend className="font-medium text-slate-700">Did MBOP read the seller listing correctly?</legend>
              <div className="mt-1 flex gap-4">
                <label className="inline-flex items-center gap-2"><input type="radio" name="parser-assessment" aria-label="Parser read correctly Yes" checked={parserAssessment === "correct"} onChange={()=>setParserAssessment("correct")} /> Yes</label>
                <label className="inline-flex items-center gap-2"><input type="radio" name="parser-assessment" aria-label="Parser read correctly No" checked={parserAssessment === "incorrect"} onChange={()=>setParserAssessment("incorrect")} /> No</label>
              </div>
            </fieldset>
            <fieldset className="text-sm">
              <legend className="font-medium text-slate-700">Does the seller listing accurately describe the item shown?</legend>
              <div className="mt-1 flex gap-4">
                <label className="inline-flex items-center gap-2"><input type="radio" name="listing-accuracy" aria-label="Listing accurate Yes" checked={sourceAccuracy === "accurate"} onChange={()=>setSourceAccuracy("accurate")} /> Yes</label>
                <label className="inline-flex items-center gap-2"><input type="radio" name="listing-accuracy" aria-label="Listing accurate No" checked={sourceAccuracy === "listing_error"} onChange={()=>setSourceAccuracy("listing_error")} /> No</label>
              </div>
            </fieldset>
            <p className="text-xs text-slate-600">The first question checks MBOP's extraction. The second records a seller description or photo problem. Neither question decides whether the Amazon and eBay products match.</p>
  </>;
}
