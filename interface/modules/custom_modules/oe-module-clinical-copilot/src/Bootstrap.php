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
use OpenEMR\Core\OEGlobalsBag;
use OpenEMR\Events\PatientDemographics\RenderEvent;
use OpenEMR\Modules\ClinicalCopilot\Controller\PanelController;
use Symfony\Component\EventDispatcher\EventDispatcherInterface;

class Bootstrap
{
    public const MODULE_INSTALLATION_PATH = "/interface/modules/custom_modules/oe-module-clinical-copilot";
    public const MODULE_NAME = "oe-module-clinical-copilot";

    private $logger;

    public function __construct(
        private readonly EventDispatcherInterface $eventDispatcher
    ) {
        $this->logger = ServiceContainer::getLogger();
    }

    public function subscribeToEvents(): void
    {
        // Render the Co-Pilot card BEFORE the patient demographic section list
        // so it is the first thing the physician sees when a chart opens — the
        // workflow described in USER.md ("a card slides into the right rail
        // within 3 seconds"). Switching from EVENT_SECTION_LIST_RENDER_AFTER
        // to _BEFORE places the card immediately above the demographics /
        // problems / meds / allergies / labs widgets.
        $this->eventDispatcher->addListener(
            RenderEvent::EVENT_SECTION_LIST_RENDER_BEFORE,
            $this->renderPanel(...)
        );
    }

    public function renderPanel(RenderEvent $event): void
    {
        $pid = $event->getPid();
        if (empty($pid)) {
            return;
        }

        try {
            $controller = new PanelController();
            echo $controller->renderPanel((int)$pid);
        } catch (\Throwable $e) {
            $this->logger->error("ClinicalCopilot: Error rendering panel", ['error' => $e->getMessage()]);
        }
    }
}
