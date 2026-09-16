import type { MatchingFeedback } from "../api/sourcing/matchingFeedback";

export function ParserReview({ parserAssessment, sourceAccuracy, setParserAssessment, setSourceAccuracy }: {
  parserAssessment: MatchingFeedback["parserAssessment"]; sourceAccuracy: MatchingFeedback["sourceAccuracy"];
  setParserAssessment: (value: MatchingFeedback["parserAssessment"]) => void;
  setSourceAccuracy: (value: MatchingFeedback["sourceAccuracy"]) => void;
}) {
  return <>
            <label className="block text-sm">Did the parser read the listing correctly?
              <select aria-label="Parser assessment" className="block w-full rounded border p-2" value={parserAssessment} onChange={e=>setParserAssessment(e.target.value as MatchingFeedback["parserAssessment"])}>
                <option value="not_reviewed">Not reviewed</option><option value="correct">Yes - parser read the source correctly</option><option value="incorrect">No - parsing error</option><option value="unsure">Not sure</option>
              </select>
            </label>
            <label className="block text-sm">Is the listing information accurate?
              <select aria-label="Listing accuracy" className="block w-full rounded border p-2" value={sourceAccuracy} onChange={e=>setSourceAccuracy(e.target.value as MatchingFeedback["sourceAccuracy"])}>
                <option value="not_reviewed">Not reviewed</option><option value="accurate">Accurate</option><option value="listing_error">Seller listing error</option><option value="unsure">Not sure</option>
              </select>
            </label>
            <p className="text-xs text-slate-600">Parser feedback is separate from product identity. Use Wrong and edit the affected field for corrections. A seller listing error does not mean the parser failed.</p>
  </>;
}
