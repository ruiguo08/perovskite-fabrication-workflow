import { Link } from "react-router-dom";
import { PageHeader } from "../components/PageHeader";
import workflowPreview from "../assets/user-workflow-sop.svg";

export function WorkflowGuidePage() {
  return (
    <div className="workflow-guide">
      <PageHeader
        title="Workflow guide"
        description="A short path from an experiment plan to J-V results and figures."
        actions={<Link className="button button--primary" to="/experiments/new">Start an experiment</Link>}
      />

      <section className="workflow-guide__setup" aria-labelledby="workflow-setup-title">
        <div>
          <span className="workflow-guide__eyebrow">Before you begin</span>
          <h2 id="workflow-setup-title">Prepare the experiment context</h2>
          <p>An active campaign and a device layout are required. Ask an instructor or administrator to prepare them if they are missing.</p>
        </div>
        <div className="workflow-guide__setup-links">
          <Link to="/campaigns">View campaigns</Link>
          <Link to="/device-layouts">View device layouts</Link>
        </div>
      </section>

      <section className="workflow-guide__overview" aria-labelledby="workflow-map-title">
        <div className="workflow-guide__section-heading">
          <div>
            <span className="workflow-guide__eyebrow">Process map</span>
            <h2 id="workflow-map-title">The full path at a glance</h2>
          </div>
          <a href={workflowPreview} target="_blank" rel="noopener noreferrer">Enlarge diagram</a>
        </div>
        <figure className="workflow-guide__figure">
          <img
            src={workflowPreview}
            alt="Archify workflow: create and submit an experiment, obtain instructor approval, release the plan, freeze and execute a fabrication batch, upload J-V data, then inspect curves or save assignments for group analysis."
            width="1112"
            height="660"
            decoding="async"
          />
          <figcaption>Static overview. Use the linked steps below to continue in the application.</figcaption>
        </figure>
      </section>

      <section aria-labelledby="workflow-steps-title">
        <div className="workflow-guide__section-heading">
          <div>
            <span className="workflow-guide__eyebrow">Working SOP</span>
            <h2 id="workflow-steps-title">Follow these steps</h2>
          </div>
        </div>
        <ol className="workflow-guide__steps">
          <li className="workflow-guide__step">
            <span className="workflow-guide__number" aria-hidden="true">01</span>
            <div className="workflow-guide__step-body">
              <span className="workflow-guide__phase">Plan · student</span>
              <h3>Create and submit a plan</h3>
              <p>Choose the campaign and device layout, define a control and target conditions, then review and save the complete recipe. Open the draft experiment and select <strong>Submit for approval</strong>.</p>
              <Link className="workflow-guide__action" to="/experiments/new">Create experiment <span aria-hidden="true">→</span></Link>
            </div>
          </li>
          <li className="workflow-guide__step">
            <span className="workflow-guide__number" aria-hidden="true">02</span>
            <div className="workflow-guide__step-body">
              <span className="workflow-guide__phase">Review · instructor, then student</span>
              <h3>Approve and release the plan</h3>
              <p>An instructor or administrator reviews the conditions and selects <strong>Approve plan</strong>. The student then opens the approved experiment and selects <strong>Release approved plan</strong>.</p>
              <Link className="workflow-guide__action" to="/experiments">Find the experiment <span aria-hidden="true">→</span></Link>
            </div>
          </li>
          <li className="workflow-guide__step">
            <span className="workflow-guide__number" aria-hidden="true">03</span>
            <div className="workflow-guide__step-body">
              <span className="workflow-guide__phase">Fabricate · student</span>
              <h3>Freeze a batch and record the work</h3>
              <p>On the experiment page, select <strong>Freeze fabrication batch</strong> before <strong>Start fabrication</strong>. In the batch run sheet, mark it ready, start execution, record actual preparations and processes, and complete the batch. Return to the experiment to complete fabrication when the work is finished.</p>
              <Link className="workflow-guide__action" to="/fabrication-batches">Open fabrication batches <span aria-hidden="true">→</span></Link>
            </div>
          </li>
          <li className="workflow-guide__step">
            <span className="workflow-guide__number" aria-hidden="true">04</span>
            <div className="workflow-guide__step-body">
              <span className="workflow-guide__phase">Characterize · student</span>
              <h3>Upload the J-V CSV</h3>
              <p>Open the experiment&apos;s <strong>Characterization results</strong> section and select <strong>Upload results</strong>. Choose the batch that produced the devices, upload its CSV, and continue to the result. The batch must be in progress or completed.</p>
              <Link className="workflow-guide__action" to="/experiments">Choose an experiment <span aria-hidden="true">→</span></Link>
            </div>
          </li>
          <li className="workflow-guide__step workflow-guide__step--analysis">
            <span className="workflow-guide__number" aria-hidden="true">05</span>
            <div className="workflow-guide__step-body">
              <span className="workflow-guide__phase">Analyze · result page</span>
              <h3>Inspect curves, then compare groups</h3>
              <p>J-V curves are available immediately after upload. Assign every substrate to its condition group and save assignments before group statistics and uniformity. Device exclusions are optional; review both all-device and filtered figures, with forward and reverse scans kept separate.</p>
              <Link className="workflow-guide__action" to="/results">Open results <span aria-hidden="true">→</span></Link>
            </div>
          </li>
        </ol>
      </section>
    </div>
  );
}
