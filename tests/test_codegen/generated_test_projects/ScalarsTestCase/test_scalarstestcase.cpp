#include <QSignalSpy>
#include <QTest>
#include <catch2/catch_test_macros.hpp>

#include "debugableclient.hpp"
#include "graphql/__generated__/MainQuery.hpp"
#include "graphql/__generated__/UserWithSameIDAndDifferentFieldsQuery.hpp"

namespace ScalarsTestCase {
using namespace qtgql;
auto ENV_NAME = QString("ScalarsTestCase");
auto SCHEMA_ADDR = get_server_address("39238999");

TEST_CASE("ScalarsTestCase", "[generated-testcase]") {
  auto env = test_utils::get_or_create_env(
      ENV_NAME, DebugClientSettings{.prod_settings = {.url = SCHEMA_ADDR}});
  auto mq = std::make_shared<mainquery::MainQuery>();
  mq->fetch();
  test_utils::wait_for_completion(mq);
  SECTION("test deserialize") {
    auto d = mq->get_data();
    REQUIRE(d->get_age() == 24);
    REQUIRE(d->get_agePoint() == 24.0f);
    REQUIRE(d->get_id() == "FakeID");
    REQUIRE(d->get_male() == true);
    REQUIRE(d->get_name() == "nir");
    REQUIRE(d->get_uuid() ==
            QUuid::fromString("06335e84-2872-4914-8c5d-3ed07d2a2f16"));
  };
  SECTION("test update") {
    auto user = mq->get_data();
    auto previous_name = mq->get_data()->get_name();
    auto modified_user_op = userwithsameidanddifferentfieldsquery::
        UserWithSameIDAndDifferentFieldsQuery::shared();
    auto catcher = test_utils::SignalCatcher({user});
    modified_user_op->fetch();
    REQUIRE(catcher.wait());
    test_utils::wait_for_completion(modified_user_op);
    REQUIRE(user->get_id() == modified_user_op->get_data()->get_id());
    auto new_name = modified_user_op->get_data()->get_name();
    REQUIRE(user->get_name() == new_name);
    REQUIRE(new_name != previous_name);
  };
  SECTION("test garbage collection") {
    std::weak_ptr<mainquery::MainQuery> weak_mq = {mq};
    auto node_id = mq->get_data()->get_id();
    auto user = ScalarsTestCase::User::INST_STORE().get_node(node_id).value();
    // the map uses count and this reference.
    REQUIRE(user.use_count() == 3);
    mq->loose();
    REQUIRE(user.use_count() == 2);
  }
};
}; // namespace ScalarsTestCase
