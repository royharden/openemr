<?php

# https://getrector.com/documentation

declare(strict_types=1);

use OpenEMR\Rector\Rules\CatchExceptionToThrowableRector;
use OpenEMR\Rector\Rules\OEGlobalsBagTypedGettersRector;
use Rector\Caching\ValueObject\Storage\FileCacheStorage;
use Rector\CodeQuality\Rector\If_\SimplifyIfElseToTernaryRector;
use Rector\CodingStyle\Rector\FuncCall\CallUserFuncArrayToVariadicRector;
use Rector\Config\RectorConfig;
use Rector\Php80\Rector\Class_\ClassPropertyAssignToConstructorPromotionRector;
use Rector\ValueObject\PhpVersion;

return RectorConfig::configure()
    ->withBootstrapFiles([
        __DIR__ . '/rector-bootstrap.php',
    ])
    ->withPaths([
        __DIR__ . '/Documentation',
        __DIR__ . '/apis',
        __DIR__ . '/ccdaservice',
        __DIR__ . '/ccr',
        __DIR__ . '/contrib',
        __DIR__ . '/controllers',
        __DIR__ . '/custom',
        __DIR__ . '/gacl',
        __DIR__ . '/interface',
        __DIR__ . '/library',
        __DIR__ . '/oauth2',
        __DIR__ . '/portal',
        __DIR__ . '/sites',
        __DIR__ . '/sphere',
        __DIR__ . '/src',
        __DIR__ . '/tests',
    ])
    ->withCache(
        // ensure file system caching is used instead of in-memory
        cacheClass: FileCacheStorage::class,
        // specify a path that works locally as well as on CI job runners
        cacheDirectory: '/tmp/rector'
    )
    ->withCodeQualityLevel(5)
    ->withConfiguredRule(ClassPropertyAssignToConstructorPromotionRector::class, [
        'allow_model_based_classes' => true,
        'inline_public' => false,
        'rename_property' => true,
    ])
    ->withDeadCodeLevel(5)
    // https://getrector.com/documentation/troubleshooting-parallel
    ->withParallel(
        timeoutSeconds: 120,
        maxNumberOfProcess: 12,
        jobSize: 12
    )
    // FIXME rector should pick the php version from composer.json
    // but that doesn't seem to be working, so hard-coding for now.
    ->withPhpVersion(PhpVersion::PHP_82)
    ->withRules([
        CallUserFuncArrayToVariadicRector::class,
        CatchExceptionToThrowableRector::class,
        OEGlobalsBagTypedGettersRector::class,
        SimplifyIfElseToTernaryRector::class,
    ])
    // Wk2 W0 cleanup (paired with AgDR-0057 phpstan baseline approach) ----
    // Bound the four mechanical Rector rules currently flagging the Wk1
    // Clinical Co-Pilot module so PR #1 unblocks Wk2 parallel teams. The
    // 14 affected files (catch (\Throwable $e), redundant (string) casts,
    // a final readonly class candidate, and a ??= op) are punch-list items
    // for Workstream A to clean as it touches each file. Per CLAUDE.md
    // ("fix existing baseline entries when modifying the file"), Workstream
    // A removes a path from below as it migrates each file. The whole
    // carve-out should be deleted before Wk3 starts.
    ->withSkip([
        // Rector wants \Exception → \Throwable (modernization), but the
        // OpenEMR custom phpstan rule ForbiddenCatchTypeRule rejects
        // catch(\Throwable) in repository/controller layers because it
        // would suppress \Error. Stick with \Exception in this module
        // (with re-throw to preserve propagation) until the phpstan rule
        // and Rector rule are reconciled — see PR #2 review notes.
        OpenEMR\Rector\Rules\CatchExceptionToThrowableRector::class => [
            __DIR__ . '/interface/modules/custom_modules/oe-module-clinical-copilot/',
        ],
        \Rector\Php80\Rector\Catch_\RemoveUnusedVariableInCatchRector::class => [
            __DIR__ . '/interface/modules/custom_modules/oe-module-clinical-copilot/',
        ],
        \Rector\DeadCode\Rector\Cast\RecastingRemovalRector::class => [
            __DIR__ . '/interface/modules/custom_modules/oe-module-clinical-copilot/',
        ],
        \Rector\Php82\Rector\Class_\ReadOnlyClassRector::class => [
            __DIR__ . '/interface/modules/custom_modules/oe-module-clinical-copilot/',
        ],
        \Rector\Php74\Rector\Assign\NullCoalescingOperatorRector::class => [
            __DIR__ . '/interface/modules/custom_modules/oe-module-clinical-copilot/',
        ],
    ])
    ->withPhpSets()
    ->withTypeCoverageLevel(5);
