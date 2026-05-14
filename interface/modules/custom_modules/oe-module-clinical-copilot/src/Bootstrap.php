<?php

/**
 * Clinical Co-Pilot Module Bootstrap
 *
 * Subscribes to PatientDemographics RenderEvent so the panel renders inside the chart.
 *
 * @package   OpenEMR
 * @author    Roy Harden <royhardenre@gmail.com>
 * @license   https://github.com/openemr/openemr/blob/master/LICENSE GNU General Public License 3
 */

declare(strict_types=1);

namespace OpenEMR\Modules\ClinicalCopilot;

use OpenEMR\BC\ServiceContainer;
use OpenEMR\Events\PatientDemographics\RenderEvent;
use OpenEMR\Events\UserInterface\PageHeadingRenderEvent;
use OpenEMR\Menu\MenuEvent;
use OpenEMR\Modules\ClinicalCopilot\Controller\IntakeUploadController;
use OpenEMR\Modules\ClinicalCopilot\Controller\PanelController;
use OpenEMR\Modules\ClinicalCopilot\Controller\UploadDocsController;
use Psr\Log\LoggerInterface;
use Symfony\Component\EventDispatcher\EventDispatcherInterface;

class Bootstrap
{
    public const MODULE_INSTALLATION_PATH = "/interface/modules/custom_modules/oe-module-clinical-copilot";
    public const MODULE_NAME = "oe-module-clinical-copilot";

    private LoggerInterface $logger;

    public function __construct(
        private readonly EventDispatcherInterface $eventDispatcher
    ) {
        $this->logger = ServiceContainer::getLogger();
    }

    public function subscribeToEvents(): void
    {
        // Plan_wk2_Claude_Next06 (refinement 2026-05-13): emit BOTH the
        // Clinical Co-Pilot card (2/3 left) and the Upload Documents card
        // (1/3 right) as a single .row out of one listener. copilot.js
        // then relocates the row above the Allergies / Medical Problems /
        // Medications three-card row on DOMContentLoaded — that gives us
        // the "above the row of three cards" placement the user wants
        // without editing core OpenEMR demographics.php.
        //
        // The event hook stays EVENT_SECTION_LIST_RENDER_BEFORE: it is
        // dispatched inside the patient-summary template's section-list
        // iterator (interface/patient_file/summary/demographics.php:1350).
        // RENDER_TOP would fire above the dashboard title — too high.
        $this->eventDispatcher->addListener(
            RenderEvent::EVENT_SECTION_LIST_RENDER_BEFORE,
            $this->renderTopRow(...)
        );

        // Plan_wk2_Claude_Next07_v2 §B.1 — pre-patient intake upload page
        // surfaces. Both listeners short-circuit when COPILOT_DEMO_MODE is
        // unset so production deployments remain invisible (AgDR-0066
        // "invisible to attackers" rationale mirrored to the menu + Finder
        // surfaces).
        $this->eventDispatcher->addListener(
            MenuEvent::MENU_UPDATE,
            $this->addIntakeUploadMenuItem(...)
        );

        // Plan_wk2_Claude_Next07_v2 §B.2 — Patient Finder PageHeading
        // affordance. Filtered to page_id='dynamic_finder' inside the
        // listener so other pages firing the same event are not modified.
        $this->eventDispatcher->addListener(
            PageHeadingRenderEvent::EVENT_PAGE_HEADING_RENDER,
            $this->addFinderIntakeButton(...)
        );
    }

    public function renderTopRow(RenderEvent $event): void
    {
        $pid = $event->getPid();
        if (!is_numeric($pid) || (int)$pid <= 0) {
            return;
        }
        $pidInt = (int)$pid;

        try {
            $copilotHtml = (new PanelController())->renderPanel($pidInt);
            // Plan_wk2_Claude_Next07_v2 follow-up (Roy decision 2026-05-14): the
            // standalone Upload Documents side-card is DEACTIVATED. The card
            // duplicated the upload form already embedded in the Co-Pilot
            // card and was reported broken on submit (form bind worked but
            // the experience was confusing). UploadDocsController stays in
            // the codebase for a Wk3+ reintegration into the Patient
            // Documents area. To reactivate inline here, replace the
            // commented invocation below and restore the col-md-8 / col-md-4
            // split.
            //
            // $uploadDocsHtml = (new UploadDocsController())->renderPanel($pidInt);
            //
            // Single-column render below: Co-Pilot card takes the full width
            // of the row so chart layout downstream of the row is unchanged.
            echo '<div class="row copilot-top-row" id="copilot-top-row">'
                . '<div class="col-md-12 p-1 copilot-top-row-main">'
                . $copilotHtml
                . '</div>'
                . '</div>';
        } catch (\RuntimeException | \LogicException $e) {
            // Plan §4.2 / AgDR-0082 — enumerated catch. The two controllers
            // can throw: RuntimeException (DB / Twig render / missing
            // template); LogicException (BadMethodCallException for a
            // missing service binding). \Error subclasses (TypeError, etc.)
            // are intentionally NOT caught so a programming bug surfaces in
            // logs rather than silently hiding behind an empty chart panel.
            $this->logger->error("ClinicalCopilot: Error rendering top-row cards", ['error' => $e->getMessage()]);
        }
    }

    /**
     * Plan_wk2_Claude_Next07_v2 §B.1 / AgDR-0090 — append a "Clinical
     * Intake Upload" entry under the Patient menu. Demo-mode gated: when
     * `COPILOT_DEMO_MODE` is unset the menu is returned unchanged, so
     * production deployments do not show the entry.
     */
    public function addIntakeUploadMenuItem(MenuEvent $event): MenuEvent
    {
        if (getenv('COPILOT_DEMO_MODE') !== '1') {
            return $event;
        }

        $menu = $event->getMenu();
        $intakeItem = new \stdClass();
        $intakeItem->requirement = 0;
        $intakeItem->target = 'pat';
        $intakeItem->menu_id = 'copilot_intake_upload';
        $intakeItem->label = xlt('Clinical Intake Upload');
        $intakeItem->url = self::MODULE_INSTALLATION_PATH . '/public/intake_upload.php';
        $intakeItem->children = [];
        // Mirrors the create_patient_from_intake.php ACL gate (AgDR-0066):
        // admin/super is the belt-and-suspenders backstop behind the
        // primary env-var safety control.
        $intakeItem->acl_req = ['admin', 'super'];

        foreach ($menu as $item) {
            // MenuEvent::getMenu() is typed `array<mixed>` upstream because
            // older callers populate it with raw stdClass / array mixes
            // depending on the menu JSON shape. Narrow defensively to a
            // stdClass with a menu_id before reading properties so PHPStan
            // level 10 is happy and we don't trip on a malformed legacy
            // entry.
            if (!$item instanceof \stdClass) {
                continue;
            }
            if (!isset($item->menu_id) || $item->menu_id !== 'patimg') {
                continue;
            }
            if (!isset($item->children) || !is_array($item->children)) {
                $item->children = [];
            }
            $item->children[] = $intakeItem;
            break;
        }

        $event->setMenu($menu);
        return $event;
    }

    /**
     * Plan_wk2_Claude_Next07_v2 §B.2 / AgDR-0091 — emit a "Upload intake
     * to create new patient (demo only)" button into the Patient Finder
     * page heading. Filtered to `page_id === 'dynamic_finder'` so other
     * pages firing the same event are untouched, and gated by
     * `COPILOT_DEMO_MODE` so production deployments do not show the
     * button.
     */
    public function addFinderIntakeButton(PageHeadingRenderEvent $event): void
    {
        if ($event->getPageId() !== 'dynamic_finder') {
            return;
        }
        if (getenv('COPILOT_DEMO_MODE') !== '1') {
            return;
        }

        $url = self::MODULE_INSTALLATION_PATH . '/public/intake_upload.php';
        $label = xlt('Upload intake to create new patient (demo only)');
        // Plain anchor styled with the standard Bootstrap btn classes;
        // appended into the title nav region via the documented
        // appendTitleNavContent helper.
        $button = sprintf(
            '<a class="btn btn-sm btn-outline-primary copilot-finder-intake-btn ml-2" href="%s"><i class="fa fa-user-plus mr-1"></i>%s</a>',
            attr($url),
            $label
        );
        $event->appendTitleNavContent($button);
    }
}
