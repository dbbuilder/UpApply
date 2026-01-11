import { useState } from 'react';
import { useAppStore } from '../store';
import { apiClient } from '../../lib/api-client';
import StepIdentity from '../components/ProfileWizard/StepIdentity';
import StepGoals from '../components/ProfileWizard/StepGoals';
import StepPreferences from '../components/ProfileWizard/StepPreferences';
import StepDealbreakers from '../components/ProfileWizard/StepDealbreakers';
import StepPricing from '../components/ProfileWizard/StepPricing';
import StepMemories from '../components/ProfileWizard/StepMemories';

const STEPS = [
  { id: 1, name: 'Identity', component: StepIdentity },
  { id: 2, name: 'Goals', component: StepGoals },
  { id: 3, name: 'Preferences', component: StepPreferences },
  { id: 4, name: 'Dealbreakers', component: StepDealbreakers },
  { id: 5, name: 'Pricing', component: StepPricing },
  { id: 6, name: 'Memories', component: StepMemories },
];

export default function SetupPage() {
  const { setupStep, setSetupStep, setCurrentView, loadProfile } = useAppStore();
  const [saving, setSaving] = useState(false);

  const currentStep = STEPS.find((s) => s.id === setupStep) || STEPS[0];
  const StepComponent = currentStep.component;
  const isLastStep = setupStep === STEPS.length;

  const handleNext = async () => {
    if (isLastStep) {
      setSaving(true);
      try {
        await apiClient.completeSetup();
        await loadProfile();
        setCurrentView('generator');
      } catch (error) {
        console.error('Failed to complete setup:', error);
      } finally {
        setSaving(false);
      }
    } else {
      const nextStep = setupStep + 1;
      setSetupStep(nextStep);
      // Update server-side step tracking
      try {
        await apiClient.updateProfile({ setup_step: nextStep } as never);
      } catch {
        // Non-critical, continue anyway
      }
    }
  };

  const handleBack = () => {
    if (setupStep > 1) {
      setSetupStep(setupStep - 1);
    }
  };

  return (
    <div className="min-h-screen flex flex-col">
      {/* Progress bar */}
      <div className="bg-white border-b p-4">
        <div className="flex items-center justify-between mb-2">
          <h2 className="font-semibold text-gray-900">Profile Setup</h2>
          <span className="text-sm text-gray-500">
            Step {setupStep} of {STEPS.length}
          </span>
        </div>
        <div className="flex gap-1">
          {STEPS.map((step) => (
            <div
              key={step.id}
              className={`h-1 flex-1 rounded-full transition-colors ${
                step.id <= setupStep ? 'bg-upwork-green' : 'bg-gray-200'
              }`}
            />
          ))}
        </div>
        <div className="mt-2 text-center text-sm font-medium text-gray-700">
          {currentStep.name}
        </div>
      </div>

      {/* Step content */}
      <div className="flex-1 overflow-auto p-4">
        <StepComponent />
      </div>

      {/* Navigation */}
      <div className="bg-white border-t p-4 flex gap-3">
        {setupStep > 1 && (
          <button type="button" onClick={handleBack} className="btn-secondary flex-1">
            Back
          </button>
        )}
        <button
          type="button"
          onClick={handleNext}
          disabled={saving}
          className="btn-primary flex-1"
        >
          {saving ? 'Saving...' : isLastStep ? 'Complete Setup' : 'Next'}
        </button>
      </div>
    </div>
  );
}
