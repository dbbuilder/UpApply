import type { JobAnalysisResponse } from '../../../lib/api-client';

function MatchScoreBadge({ score }: { score: number }) {
  let colorClass = 'score-low';
  let label = 'Low Match';
  if (score >= 80) { colorClass = 'score-excellent'; label = 'Excellent'; }
  else if (score >= 65) { colorClass = 'score-good'; label = 'Good'; }
  else if (score >= 50) { colorClass = 'score-moderate'; label = 'Moderate'; }
  return (
    <div className="text-center">
      <div className={`text-3xl font-bold ${colorClass}`}>{score}%</div>
      <div className="text-sm text-gray-500">{label}</div>
    </div>
  );
}

interface AnalysisPanelProps {
  jobAnalysis: JobAnalysisResponse | null;
  analysisLoading: boolean;
  analysisError: string | null;
  onAnalyze: () => void;
  addedSkills: Set<string>;
  addingSkill: string | null;
  onAddMissingSkill: (skill: string) => void;
}

export default function AnalysisPanel({
  jobAnalysis,
  analysisLoading,
  analysisError,
  onAnalyze,
  addedSkills,
  addingSkill,
  onAddMissingSkill,
}: AnalysisPanelProps) {
  return (
    <>
      {/* Analysis Error */}
      {analysisError && (
        <div className="card bg-red-50 border-red-200">
          <h4 className="font-medium text-red-800 mb-1">Analysis Failed</h4>
          <p className="text-sm text-red-700">{analysisError}</p>
          <button type="button" onClick={onAnalyze} className="btn-outline text-sm mt-2">
            Retry
          </button>
        </div>
      )}

      {/* Analyze button */}
      {!jobAnalysis && !analysisLoading && !analysisError && (
        <button type="button" onClick={onAnalyze} className="btn-outline w-full">
          Analyze Job Match
        </button>
      )}

      {/* Loading */}
      {analysisLoading && (
        <div className="card text-center py-6">
          <div className="animate-pulse-slow text-gray-500">Analyzing job...</div>
        </div>
      )}

      {/* Result */}
      {jobAnalysis && (
        <div className="card animate-slide-up">
          <div className="flex items-center justify-between mb-4">
            <h4 className="font-medium text-gray-900">Match Analysis</h4>
            <MatchScoreBadge score={jobAnalysis.match_score} />
          </div>

          <p className="text-sm text-gray-600 mb-3">{jobAnalysis.recommendation}</p>

          {jobAnalysis.deal_breaker_warnings.length > 0 && (
            <div className="bg-red-50 rounded-lg p-3 mb-3">
              <h5 className="text-sm font-medium text-red-800 mb-1">Warnings</h5>
              <ul className="text-sm text-red-700 space-y-1">
                {jobAnalysis.deal_breaker_warnings.map((warning, i) => (
                  <li key={i}>&#8226; {warning}</li>
                ))}
              </ul>
            </div>
          )}

          {jobAnalysis.strengths.length > 0 && (
            <div className="mb-3">
              <h5 className="text-sm font-medium text-gray-700 mb-1">Strengths</h5>
              <ul className="text-sm text-gray-600 space-y-1">
                {jobAnalysis.strengths.map((strength, i) => (
                  <li key={i} className="text-green-600">&#10003; {strength}</li>
                ))}
              </ul>
            </div>
          )}

          {jobAnalysis.concerns.length > 0 && (
            <div className="mb-3">
              <h5 className="text-sm font-medium text-gray-700 mb-1">Concerns</h5>
              <ul className="text-sm text-gray-600 space-y-1">
                {jobAnalysis.concerns.map((concern, i) => (
                  <li key={i} className="text-yellow-600">! {concern}</li>
                ))}
              </ul>
            </div>
          )}

          {jobAnalysis.skill_matches.length > 0 && (
            <div>
              <h5 className="text-sm font-medium text-gray-700 mb-1">Matching Skills</h5>
              <div className="flex flex-wrap gap-1">
                {jobAnalysis.skill_matches.map((match) => (
                  <span
                    key={match.skill}
                    className={`badge ${match.match_type === 'exact' ? 'badge-green' : 'badge-yellow'}`}
                  >
                    {match.skill}{match.user_level && ` (${match.user_level})`}
                  </span>
                ))}
              </div>
            </div>
          )}

          {jobAnalysis.missing_skills.length > 0 && (
            <div className="mt-2">
              <h5 className="text-sm font-medium text-gray-700 mb-1">Missing Skills</h5>
              <div className="flex flex-wrap gap-1">
                {jobAnalysis.missing_skills.map((skill) => (
                  <span key={skill} className="badge badge-red inline-flex items-center gap-1">
                    {skill}
                    {addedSkills.has(skill) ? (
                      <span className="text-green-600 text-xs" title="Added to profile">&#10003;</span>
                    ) : (
                      <button
                        type="button"
                        onClick={() => onAddMissingSkill(skill)}
                        disabled={addingSkill === skill}
                        className="text-red-400 hover:text-green-600 text-xs font-bold ml-0.5"
                        title="Add to profile"
                      >
                        {addingSkill === skill ? '...' : '+'}
                      </button>
                    )}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </>
  );
}
