# Changelog

## [2.10.0](https://github.com/mossipcams/autodoctor/compare/v2.9.0...v2.10.0) (2026-01-31)


### Features

* **004:** validate entity IDs in service call targets ([7a23f5b](https://github.com/mossipcams/autodoctor/commit/7a23f5bbef4c6c5628d54f4579043d405ee81da5))
* dynamic versioning from manifest.json and CI card rebuild ([5f78c0a](https://github.com/mossipcams/autodoctor/commit/5f78c0acbf231ed5753edf7809a96c654f8983e8))


### Bug Fixes

* **003:** replace brittle substring heuristics with platform-based Bermuda detection ([10d9e81](https://github.com/mossipcams/autodoctor/commit/10d9e814c11226f62b38e335cef60389c725d180))
* **004:** remove dead knowledge_base parameter from JinjaValidator.__init__ ([8078d4d](https://github.com/mossipcams/autodoctor/commit/8078d4d49540667bafb8307f615d8a07fc4423e8))
* **004:** remove sensor.native_value and native_unit_of_measurement from domain_attributes ([2aa946a](https://github.com/mossipcams/autodoctor/commit/2aa946a8fe92c015a433aa4fb628d175b41ad464))
* **004:** replace Bermuda substring matching with entity registry platform lookup ([49fad0a](https://github.com/mossipcams/autodoctor/commit/49fad0a47786b26936ae44a39b4cc37276fbec31))
* **004:** widen STATE_VALIDATION_WHITELIST to include lock, cover, alarm_control_panel, climate ([c3df079](https://github.com/mossipcams/autodoctor/commit/c3df079aac810a61e8edf4931aa976ed7851baa1))
* **quick-002:** pass shared knowledge_base to JinjaValidator in __init__.py ([4e17add](https://github.com/mossipcams/autodoctor/commit/4e17add2146d9c75eda86855e5419f2b85d173e8))
* resolve merge conflicts with main (PR [#36](https://github.com/mossipcams/autodoctor/issues/36) Bermuda detection) ([93f2f5b](https://github.com/mossipcams/autodoctor/commit/93f2f5bb7a7b68e57c8ffa948a3945776470ee4c))
* **validation:** Phase 13 — fix 21 validation correctness defects ([91a6b4c](https://github.com/mossipcams/autodoctor/commit/91a6b4c236443727595f45917e3c202c4c4aae23))


### Code Refactoring

* **004:** extract shared _check_state_value helper in validator.py ([59af8f3](https://github.com/mossipcams/autodoctor/commit/59af8f3125501e67b47a7b781af1d76ae17d9a61))


### Documentation

* **004:** add order-dependency comment to _dedup_cross_family ([e8038ab](https://github.com/mossipcams/autodoctor/commit/e8038ab6285b1f9ce351b1da043252537c149c8f))

## [2.9.0](https://github.com/mossipcams/autodoctor/compare/v2.8.0...v2.9.0) (2026-01-30)


### Features

* dynamic versioning from manifest.json and CI card rebuild ([4fb8555](https://github.com/mossipcams/autodoctor/commit/4fb8555fc7bd2806ad99ed827df16448557730b9))

## [2.8.0](https://github.com/mossipcams/autodoctor/compare/v2.7.0...v2.8.0) (2026-01-30)


### Features

* **08-01:** add async_validate_all_with_groups() to __init__.py ([66f3f83](https://github.com/mossipcams/autodoctor/commit/66f3f83918b336a74bbfb62fd991c3a8d0a76b2f))
* **08-01:** add run_steps and steps WS handlers to websocket_api.py ([1377632](https://github.com/mossipcams/autodoctor/commit/1377632314e6dfd533275cb9641ac11f855d946a))
* **08-01:** add VALIDATION_GROUPS mapping and VALIDATION_GROUP_ORDER to models.py ([c0610ed](https://github.com/mossipcams/autodoctor/commit/c0610ed97a23d7e10ae7dd173e6a01fe70bd2e36))
* **09-01:** extract autodoc-issue-group sub-component ([4de36b3](https://github.com/mossipcams/autodoctor/commit/4de36b3c7b36e070e83ff696dc40590dacb16647))
* **09-01:** extract shared styles and badge helpers ([76bbd60](https://github.com/mossipcams/autodoctor/commit/76bbd6048e4a8e083bbca665d5bccb120ed3d013))
* **10-01:** add ValidationGroup/StepsResponse types and pipeline CSS styles ([44d3eae](https://github.com/mossipcams/autodoctor/commit/44d3eaeff06bfdf47a34f99462a3cda27b3d035f))
* **10-01:** create pipeline component and integrate into parent card ([f4791da](https://github.com/mossipcams/autodoctor/commit/f4791da1e2c27dfe559c3c6b65b821129d4d55fa))
* **11-01:** add neutral/active CSS states, remove spinner styles, rebuild JS ([1377aae](https://github.com/mossipcams/autodoctor/commit/1377aae53b3f82fae5e5e618b07337641e5db429))
* **11-01:** add stagger state machine and lifecycle hooks to autodoc-pipeline ([8df489d](https://github.com/mossipcams/autodoctor/commit/8df489d623dc82709b16e12051747a4cdbd5efae))
* **v2.7.0:** replace hardcoded Jinja2 sets with dataclass catalog, expand service params ([d6290c7](https://github.com/mossipcams/autodoctor/commit/d6290c7790549c386a2f3cbfb014a7ed468fe746))


### Bug Fixes

* **02-01:** switch to mutmut 2.x for macOS/Python 3.14 compatibility ([8e94442](https://github.com/mossipcams/autodoctor/commit/8e94442bcb843acd1aa003180e789f8b16778580))
* **02-01:** switch to mutmut 3.x with also_copy and conftest compatibility ([b1453d8](https://github.com/mossipcams/autodoctor/commit/b1453d869cfd8e64c7765e4dac5b1697a8b650b7))
* **09-01:** remove dead conflicts tab code from TS source ([8b9c44c](https://github.com/mossipcams/autodoctor/commit/8b9c44c908ef098353de4735cdcaa498352adecd))
* **quick-001:** fix options.get() TypeError and wrong config key ([96225dc](https://github.com/mossipcams/autodoctor/commit/96225dc1686eced88c92bd38f3b26a2e1976cf35))
* **quick-001:** fix options.get() TypeError and wrong config key ([711de81](https://github.com/mossipcams/autodoctor/commit/711de810ba62cd7e3477993e72610862850dffe4))
* **quick-001:** remove unused AutodoctorData and ValidationConfig from models.py ([1c6c4f2](https://github.com/mossipcams/autodoctor/commit/1c6c4f20543f619c98b15eb2f7204511550951da))
* **quick-001:** remove unused AutodoctorData and ValidationConfig from models.py ([2f89168](https://github.com/mossipcams/autodoctor/commit/2f89168e1a86b6f5e09b7ec8481f084723c8947e))
* **quick-001:** rename shadowed MAX_RECURSION_DEPTH in jinja_validator.py ([0e37a47](https://github.com/mossipcams/autodoctor/commit/0e37a470c9846bd575fc19f45a0fe79601f7819f))
* **quick-001:** rename shadowed MAX_RECURSION_DEPTH in jinja_validator.py ([30ce350](https://github.com/mossipcams/autodoctor/commit/30ce35003645d30f9168e2a20d37e1025616bee3))
* reduce false positives with 6-phase validation narrowing ([0aaa2b2](https://github.com/mossipcams/autodoctor/commit/0aaa2b239865c9b1d91ae0487d6a480e18795fde))
* reduce false positives with 6-phase validation narrowing ([4644ac9](https://github.com/mossipcams/autodoctor/commit/4644ac9be3877e0cfeed54a3a04784c7da7c3906))
* repair corrupted config_flow schema and update index.md ([c5fb739](https://github.com/mossipcams/autodoctor/commit/c5fb73947d2bf2b786304e59c47a6d0c0ebc404e))
* resolve service validation false positives for list params and capability-dependent params ([9f38e51](https://github.com/mossipcams/autodoctor/commit/9f38e519068a6ea7815f02080ac82427488aba7d))


### Code Refactoring

* **01-01:** remove dead code from jinja_validator.py ([cc3256d](https://github.com/mossipcams/autodoctor/commit/cc3256d6ab32e3359a218a07161051fb9cf19c23))
* **01-01:** rename test_fix_engine.py and clean up fix_engine references ([498ddaf](https://github.com/mossipcams/autodoctor/commit/498ddaf2dd50cb1324410df9214cad8f184cb035))
* **09-01:** slim autodoctor-card.ts from 1529 to 645 lines ([db27b0c](https://github.com/mossipcams/autodoctor/commit/db27b0c6f7c0051d36c4b0b36135772145530aa2))
* **12:** tech debt review and cleanup ([1ef1bb0](https://github.com/mossipcams/autodoctor/commit/1ef1bb07b272ca058aa54a75ff0674138fa608b3))
* implement architectural review recommendations ([708d2af](https://github.com/mossipcams/autodoctor/commit/708d2af27491e5fc7ce97cdb6ce1f8670efa4504))
* remove dead code from template_semantics.py and update index.md ([145df7b](https://github.com/mossipcams/autodoctor/commit/145df7b6c53d7b44fe7665c270d439fdc54ce370))


### Documentation

* **08-01:** update index.md with new WS commands ([6d183c2](https://github.com/mossipcams/autodoctor/commit/6d183c28dcf3abf29ea577d7898b5f38ce8015de))
* **10-01:** update index.md with frontend source file listing ([4ed08c1](https://github.com/mossipcams/autodoctor/commit/4ed08c1c0e6c4fad988c625a03c872a2db4f6adb))
* add strict validation options to README ([ecb2713](https://github.com/mossipcams/autodoctor/commit/ecb27130c8568f73a1ca84852fd7d968b19f3370))
* initialize project ([869f56c](https://github.com/mossipcams/autodoctor/commit/869f56cbcd610728bed13feed4bb78a26f056347))
* map existing codebase ([1b683b5](https://github.com/mossipcams/autodoctor/commit/1b683b59639e7d8cefb9d7a063db776c79f302a9))
* update PROJECT.md with v2.7.0 roadmap and traceability ([b20462d](https://github.com/mossipcams/autodoctor/commit/b20462da17aa5c6f331eb1a1d1b758c4052d0cf5))

## [2.7.0](https://github.com/mossipcams/autodoctor/compare/v2.6.2...v2.7.0) (2026-01-30)


### Features

* add full service call parameter validation ([9836c37](https://github.com/mossipcams/autodoctor/commit/9836c379d9ccdc11f6683b066c3f989703568124))


### Bug Fixes

* validate device/area/tag/integration references against correct registries ([6360401](https://github.com/mossipcams/autodoctor/commit/6360401ea41046a685dde7ed76a1f91e52dd6b39))

## [2.6.2](https://github.com/mossipcams/autodoctor/compare/v2.6.1...v2.6.2) (2026-01-30)


### Bug Fixes

* resolve false positive undefined variable warnings for callable globals and sequence variables ([40c2f59](https://github.com/mossipcams/autodoctor/commit/40c2f593b86c0ffd3467ef4c883eebf3773cd74d))

## [2.6.1](https://github.com/mossipcams/autodoctor/compare/v2.6.0...v2.6.1) (2026-01-30)


### Bug Fixes

* resolve false positive undefined variable warnings for blueprint automations ([9baa3d9](https://github.com/mossipcams/autodoctor/commit/9baa3d985ea0ac7bf5773fd6d81c8085e7ebf7ed))

## [2.6.0](https://github.com/mossipcams/autodoctor/compare/v2.5.0...v2.6.0) (2026-01-30)


### Features

* add regex patterns for helper function extraction ([a54a77e](https://github.com/mossipcams/autodoctor/commit/a54a77e8456321648c6cf8021dd8df6547f728f9))
* extract entity references from for-each iterations ([8a41e3c](https://github.com/mossipcams/autodoctor/commit/8a41e3ccd6158c91afaa40f8ec2361123fdb68da))
* extract entity references from helper functions ([45ffd54](https://github.com/mossipcams/autodoctor/commit/45ffd5490158e962bf81c39adb2ac79f5795b007))
* extract entity references from service calls ([5926b0a](https://github.com/mossipcams/autodoctor/commit/5926b0a6a0561ed19ce0102f3af2eea65a8a0ca5))
* extract script references from shorthand syntax ([5f40fe0](https://github.com/mossipcams/autodoctor/commit/5f40fe0233307c8c726225605ad2ec14158b7029))


### Documentation

* mark state extraction improvements as implemented ([5ab5521](https://github.com/mossipcams/autodoctor/commit/5ab5521c580df427d0e74d62eb737a45aed5c0a3))

## [2.5.0](https://github.com/mossipcams/autodoctor/compare/v2.4.0...v2.5.0) (2026-01-29)


### Features

* add AST-based Jinja2 validation with unknown filter/test detection ([2db4b71](https://github.com/mossipcams/autodoctor/commit/2db4b716eafb1f6eef03657d513accbdff18e3e7))
* add error handling to validation pipeline ([0568cbd](https://github.com/mossipcams/autodoctor/commit/0568cbd1c0926d67378c058b1cd6b2f4cb663d2d))
* add get_integration helper to knowledge base ([e2fa354](https://github.com/mossipcams/autodoctor/commit/e2fa35428937e46ed3dff5405538a443fea2c06e))
* add LearnedStatesStore for persisting user-learned states ([7b95830](https://github.com/mossipcams/autodoctor/commit/7b958305a1aee57c08d6341b3d09b4a0efc0c94a))
* add script to extract states from HA source ([0fd7ef4](https://github.com/mossipcams/autodoctor/commit/0fd7ef4cb97c17d806c67ad4659dbd56d65a8b30))
* conflict detection and mvp refactor ([d59ee58](https://github.com/mossipcams/autodoctor/commit/d59ee58218b5970d55b3c7c4cceba00ddc2df6c6))
* enhance validation system with four improvements ([aa16922](https://github.com/mossipcams/autodoctor/commit/aa16922569c463c13e52c339aa786a6b06b43a39))
* foundation and core validation engine ([c32c6d7](https://github.com/mossipcams/autodoctor/commit/c32c6d716ee5640c7247c38568845257aee3eaef))
* home assistant integration ([42f09e8](https://github.com/mossipcams/autodoctor/commit/42f09e89a4b9b2c30ad75623a1178299d972e53c))
* implement capability-based state and attribute validation ([9ccf9d0](https://github.com/mossipcams/autodoctor/commit/9ccf9d0b424e4daa4feb1ef4753e84bbb2aed9fb))
* initialize LearnedStatesStore in integration setup ([b219a81](https://github.com/mossipcams/autodoctor/commit/b219a819ac813dc6337bcfc5c2355617257c9bc3))
* integrate learned states into knowledge base validation ([c2c0125](https://github.com/mossipcams/autodoctor/commit/c2c01259377363fcea3495096d47cb61490ea343))
* jinja validation and smart condition tracking ([4076b45](https://github.com/mossipcams/autodoctor/commit/4076b450a70a38cabb8b6131b0304e84870a0f1d))
* learn states when suppressing invalid_state issues ([eb64965](https://github.com/mossipcams/autodoctor/commit/eb649653150c8bf4dbda243758d3cf4c59457f24))
* **models:** fix ValidationIssue hash/eq for set operations ([a6c99f1](https://github.com/mossipcams/autodoctor/commit/a6c99f1ff3302436098983b824c9890d65f25262))
* validation pipeline hardening (Phase 1-2) ([cee420f](https://github.com/mossipcams/autodoctor/commit/cee420f7539911b8a9032baa33c18bd4f213dff8))
* websocket api and frontend card ([4387cd6](https://github.com/mossipcams/autodoctor/commit/4387cd61c9111507b2ba7e0e2f21962309b6bc15))


### Bug Fixes

* clean up issue types - implement ATTRIBUTE_NOT_FOUND and remove IMPOSSIBLE_CONDITION ([d8ff86f](https://github.com/mossipcams/autodoctor/commit/d8ff86fc4d56f55faee024448f99bbfe9b871b5c))
* improve HA best practices compliance ([8594284](https://github.com/mossipcams/autodoctor/commit/8594284b91b406699768afac562227dac088fd3f))
* repairs not showing in HA and remove refresh button ([f0a7a8f](https://github.com/mossipcams/autodoctor/commit/f0a7a8fe0d47861a6972e2be5a5804ac1444f5b1))
* use generic type for const.py in release-please config ([2b1fae3](https://github.com/mossipcams/autodoctor/commit/2b1fae3972dffe5f0dfd3ecd35e16d1797029ebe))


### Performance Improvements

* optimize knowledge base performance ([2c9df92](https://github.com/mossipcams/autodoctor/commit/2c9df92639609a7605b05d7ebef75b02e0250f13))


### Code Refactoring

* improve code quality and reduce duplication ([414c64e](https://github.com/mossipcams/autodoctor/commit/414c64ef50674c7c58c08ee1370e51aa4e60f00f))
* remove conflict detection and state suggestion features ([edabb5b](https://github.com/mossipcams/autodoctor/commit/edabb5baa428ae18ecb5a70c2d5a831708fb3e4b))
* remove conflicts tab from frontend ([8417b53](https://github.com/mossipcams/autodoctor/commit/8417b5395bb132449dd87d82c19107da619a08dd))
* remove unused simulator module ([7d3901b](https://github.com/mossipcams/autodoctor/commit/7d3901b7936fc1084d1126a6da7983db6499601b))
* simplify cache-busting and sync VERSION across files ([712f6d4](https://github.com/mossipcams/autodoctor/commit/712f6d4b8090c661f3c1939e5cadb9e04b4242e9))


### Documentation

* add state validation implementation plan ([280a912](https://github.com/mossipcams/autodoctor/commit/280a9120d3db5c7235e0639e0e68c41c29df73aa))
* add state validation improvements design ([e9f7519](https://github.com/mossipcams/autodoctor/commit/e9f7519c78256edd8ca3b5fa541a54c841e1cf63))
* add validation pipeline hardening design ([5bc792c](https://github.com/mossipcams/autodoctor/commit/5bc792c2a348618a666815b231bcb5ba8dd55f27))
* update index with new state learning modules ([158e16d](https://github.com/mossipcams/autodoctor/commit/158e16d68dfb243989eeb371cf6a866b98400b50))
* update README with user-focused problem statement and v2.1 features ([aebdf11](https://github.com/mossipcams/autodoctor/commit/aebdf11fe0e67f1b13ad3b8f11a647f0dea97ff4))

## [2.4.0](https://github.com/mossipcams/autodoctor/compare/v2.3.0...v2.4.0) (2026-01-29)


### Features

* add capability source constants for state vs attribute separation ([c972699](https://github.com/mossipcams/autodoctor/commit/c97269931a7cc77394413fc87f51c09762efd9a8))
* implement _get_capabilities_states() for select/climate entities ([cea9312](https://github.com/mossipcams/autodoctor/commit/cea93126ce001527f5fc57b0cd89fb14a5b09177))
* **jinja:** add AST-based semantic validation for unknown filters and tests ([c30308f](https://github.com/mossipcams/autodoctor/commit/c30308f5739296943cd3c5b30984cb5901dfb8e1))
* **models:** add TEMPLATE_UNKNOWN_FILTER and TEMPLATE_UNKNOWN_TEST issue types ([b221173](https://github.com/mossipcams/autodoctor/commit/b22117322c837ad7f4815f6a12730397a5491a16))


### Bug Fixes

* clean up issue types - implement ATTRIBUTE_NOT_FOUND and remove unused IMPOSSIBLE_CONDITION ([afdc3ea](https://github.com/mossipcams/autodoctor/commit/afdc3eaa55693f288c6f48979811bc55b0a8963c))
* **jinja:** add loopcontrols extension to prevent false positives on break/continue ([dd3b80b](https://github.com/mossipcams/autodoctor/commit/dd3b80b04f0abd9068a4f32e1238a62731d0b6c6))


### Code Refactoring

* delete conflict detection module and tests ([1cda7f8](https://github.com/mossipcams/autodoctor/commit/1cda7f8838a938187371bde2aa7a4b469a3fe754))
* remove conflict detection data models ([603dc88](https://github.com/mossipcams/autodoctor/commit/603dc881910309dcaa457225574f71f51f8cf764))
* remove conflict detection methods from analyzer ([b3abf1f](https://github.com/mossipcams/autodoctor/commit/b3abf1f4df6328bbe6d48ec40057f00fbda43dec))
* remove conflict detection WebSocket handlers ([ec74cee](https://github.com/mossipcams/autodoctor/commit/ec74ceec2b7d68c0f71d9505bb84e318b0013ede))
* remove state suggestion feature ([16ce749](https://github.com/mossipcams/autodoctor/commit/16ce7493277a82f3b1f1ea631b091ff2464b3578))
* remove unused simulator module and service ([331b37d](https://github.com/mossipcams/autodoctor/commit/331b37d3c043f9683b45096f6d3ad8f611f93070))


### Documentation

* design for removing state suggestions and conflict detection ([02adf61](https://github.com/mossipcams/autodoctor/commit/02adf61a3f33cfba8bfea8ca3290781303cbd2be))
* implementation plan for removing state suggestions and conflicts ([e829f22](https://github.com/mossipcams/autodoctor/commit/e829f222d821bec153187c52241ccbb8f1e11f37))
* update index.md to remove conflict detection references ([cf12dac](https://github.com/mossipcams/autodoctor/commit/cf12dac2288186818fcda21c5cb2e0ec213aca54))
* update index.md with new validation rules and test file ([79f9f26](https://github.com/mossipcams/autodoctor/commit/79f9f26aae11fba3cf45fe0c12d4793c0bec0d8d))
* update README to remove state suggestions and conflict detection ([38597d9](https://github.com/mossipcams/autodoctor/commit/38597d9ecd3d5c530303aa901c7ade24ac2dcaf8))

## [2.3.0](https://github.com/mossipcams/autodoctor/compare/v2.2.0...v2.3.0) (2026-01-29)


### Features

* enhance validation system with four improvements ([aa16922](https://github.com/mossipcams/autodoctor/commit/aa16922569c463c13e52c339aa786a6b06b43a39))

## [2.2.0](https://github.com/mossipcams/autodoctor/compare/v2.1.0...v2.2.0) (2026-01-28)


### Features

* add error handling to validation pipeline ([0568cbd](https://github.com/mossipcams/autodoctor/commit/0568cbd1c0926d67378c058b1cd6b2f4cb663d2d))
* **models:** fix ValidationIssue hash/eq for set operations ([a6c99f1](https://github.com/mossipcams/autodoctor/commit/a6c99f1ff3302436098983b824c9890d65f25262))
* validation pipeline hardening (Phase 1-2) ([cee420f](https://github.com/mossipcams/autodoctor/commit/cee420f7539911b8a9032baa33c18bd4f213dff8))


### Bug Fixes

* repairs not showing in HA and remove refresh button ([f0a7a8f](https://github.com/mossipcams/autodoctor/commit/f0a7a8fe0d47861a6972e2be5a5804ac1444f5b1))


### Performance Improvements

* optimize knowledge base performance ([2c9df92](https://github.com/mossipcams/autodoctor/commit/2c9df92639609a7605b05d7ebef75b02e0250f13))


### Code Refactoring

* improve code quality and reduce duplication ([414c64e](https://github.com/mossipcams/autodoctor/commit/414c64ef50674c7c58c08ee1370e51aa4e60f00f))


### Documentation

* add validation pipeline hardening design ([5bc792c](https://github.com/mossipcams/autodoctor/commit/5bc792c2a348618a666815b231bcb5ba8dd55f27))
* update README with user-focused problem statement and v2.1 features ([aebdf11](https://github.com/mossipcams/autodoctor/commit/aebdf11fe0e67f1b13ad3b8f11a647f0dea97ff4))

## [2.1.0](https://github.com/mossipcams/autodoctor/compare/v2.0.0...v2.1.0) (2026-01-28)


### Features

* add get_integration helper to knowledge base ([e2fa354](https://github.com/mossipcams/autodoctor/commit/e2fa35428937e46ed3dff5405538a443fea2c06e))
* add LearnedStatesStore for persisting user-learned states ([7b95830](https://github.com/mossipcams/autodoctor/commit/7b958305a1aee57c08d6341b3d09b4a0efc0c94a))
* add script to extract states from HA source ([0fd7ef4](https://github.com/mossipcams/autodoctor/commit/0fd7ef4cb97c17d806c67ad4659dbd56d65a8b30))
* conflict detection and mvp refactor ([d59ee58](https://github.com/mossipcams/autodoctor/commit/d59ee58218b5970d55b3c7c4cceba00ddc2df6c6))
* foundation and core validation engine ([c32c6d7](https://github.com/mossipcams/autodoctor/commit/c32c6d716ee5640c7247c38568845257aee3eaef))
* home assistant integration ([42f09e8](https://github.com/mossipcams/autodoctor/commit/42f09e89a4b9b2c30ad75623a1178299d972e53c))
* initialize LearnedStatesStore in integration setup ([b219a81](https://github.com/mossipcams/autodoctor/commit/b219a819ac813dc6337bcfc5c2355617257c9bc3))
* integrate learned states into knowledge base validation ([c2c0125](https://github.com/mossipcams/autodoctor/commit/c2c01259377363fcea3495096d47cb61490ea343))
* jinja validation and smart condition tracking ([4076b45](https://github.com/mossipcams/autodoctor/commit/4076b450a70a38cabb8b6131b0304e84870a0f1d))
* learn states when suppressing invalid_state issues ([eb64965](https://github.com/mossipcams/autodoctor/commit/eb649653150c8bf4dbda243758d3cf4c59457f24))
* websocket api and frontend card ([4387cd6](https://github.com/mossipcams/autodoctor/commit/4387cd61c9111507b2ba7e0e2f21962309b6bc15))


### Bug Fixes

* improve HA best practices compliance ([8594284](https://github.com/mossipcams/autodoctor/commit/8594284b91b406699768afac562227dac088fd3f))


### Documentation

* add state validation implementation plan ([280a912](https://github.com/mossipcams/autodoctor/commit/280a9120d3db5c7235e0639e0e68c41c29df73aa))
* add state validation improvements design ([e9f7519](https://github.com/mossipcams/autodoctor/commit/e9f7519c78256edd8ca3b5fa541a54c841e1cf63))
* update index with new state learning modules ([158e16d](https://github.com/mossipcams/autodoctor/commit/158e16d68dfb243989eeb371cf6a866b98400b50))
