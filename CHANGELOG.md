# Changelog

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
